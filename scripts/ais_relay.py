#!/usr/bin/env python3
"""AIS Relay Script - local sender side.

Runs on a machine that is on the same LAN as Boat Beacon. Discovers the
Boat Beacon TCP NMEA feed automatically, then forwards every received
line over a raw TCP push connection to the River Watch GCP collector.

Typical usage (no Boat Beacon IP needed):

    COLLECTOR_IP=34.172.47.153 COLLECTOR_PORT=6000 python3 scripts/ais_relay.py

If you already know the Boat Beacon address you can skip the scan:

    BOAT_BEACON_IP=192.168.1.42 BOAT_BEACON_PORT=7000 \
    COLLECTOR_IP=34.172.47.153 COLLECTOR_PORT=6000 python3 scripts/ais_relay.py

The discovery scan:
  * enumerates the host's local IPv4 subnets via /proc/net/route
  * skips loopback (127/8), link-local (169.254/16), 0/8 and any
    interface that looks like a Docker / VPN bridge
  * probes ports 5353, 7000, 10110, 10111, 4001, 4002, 5000, 5001, 8080, 8088
  * reads a 2-second sample and classifies AIS / NMEA payloads
  * picks the highest-confidence candidate

The last successful Boat Beacon address is cached to
~/.riverwatch_ais_relay.json and tried first on the next launch.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import select
import signal
import socket
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOAT_BEACON_IP = os.environ.get("BOAT_BEACON_IP", "").strip()
BOAT_BEACON_PORT_RAW = os.environ.get("BOAT_BEACON_PORT", "").strip()
BOAT_BEACON_PORT = int(BOAT_BEACON_PORT_RAW) if BOAT_BEACON_PORT_RAW else None

COLLECTOR_IP = os.environ.get("COLLECTOR_IP", "34.172.47.153")
COLLECTOR_PORT = int(os.environ.get("COLLECTOR_PORT", "6000"))

SCAN_PORTS: Tuple[int, ...] = (
    5353, 7000, 10110, 10111, 4001, 4002, 5000, 5001, 8080, 8088,
)
SCAN_CONNECT_TIMEOUT = float(os.environ.get("SCAN_CONNECT_TIMEOUT", "0.6"))
SCAN_READ_TIMEOUT = float(os.environ.get("SCAN_READ_TIMEOUT", "2.0"))
SCAN_READ_BYTES = int(os.environ.get("SCAN_READ_BYTES", "512"))
SCAN_CONCURRENCY = int(os.environ.get("SCAN_CONCURRENCY", "64"))
SCAN_MAX_HOSTS = int(os.environ.get("SCAN_MAX_HOSTS", "512"))

# Optional cap for which interfaces to look at. Comma-separated, e.g.
# IFACE_ALLOWLIST="eth0,wlan0"
IFACE_ALLOWLIST = [
    s.strip() for s in os.environ.get("IFACE_ALLOWLIST", "").split(",") if s.strip()
]
SUBNET_OVERRIDE = os.environ.get("BOAT_BEACON_SUBNET", "").strip()

DOCKER_IFACE_PREFIXES = (
    "docker", "br-", "veth", "cni", "flannel", "weave", "cali", "tun", "tap", "vxlan",
)

AIS_SENTENCE_RE = re.compile(rb"\!(AIVDM|AIVDO|BSVDM|BSVDO|ABVDM|ABVDO)")
NMEA_SENTENCE_RE = re.compile(rb"\$(GPRMC|GPGGA|GPGLL|GPVTG|GPGSV)")

CACHE_PATH = Path(os.environ.get(
    "AIS_RELAY_CACHE",
    str(Path.home() / ".riverwatch_ais_relay.json"),
))

RECONNECT_DELAY = 5  # seconds

stats: Dict[str, object] = {
    "lines_relayed": 0,
    "bytes_relayed": 0,
    "start_time": None,
    "last_data_time": None,
    "errors": 0,
}

running = True


def _handle_sigint(_sig, _frame):
    global running
    log("Shutting down...")
    running = False
    sys.exit(0)


signal.signal(signal.SIGINT, _handle_sigint)
signal.signal(signal.SIGTERM, _handle_sigint)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Network discovery helpers
# ---------------------------------------------------------------------------

def _looks_dockerish(iface: str) -> bool:
    return any(iface.startswith(p) for p in DOCKER_IFACE_PREFIXES)


def _parse_proc_net_route() -> List[dict]:
    """Return [{iface, network(CIDR), gateway, is_default}, ...] from /proc/net/route."""
    rows: List[dict] = []
    try:
        with open("/proc/net/route", "r") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return rows
    for raw in lines[1:]:
        parts = raw.split()
        if len(parts) < 8:
            continue
        iface, dest_hex, gw_hex, _flags, _refcnt, _use, _metric, mask_hex = parts[:8]
        try:
            dest = socket.inet_ntoa(struct.pack("<L", int(dest_hex, 16)))
            mask = socket.inet_ntoa(struct.pack("<L", int(mask_hex, 16)))
            gw = socket.inet_ntoa(struct.pack("<L", int(gw_hex, 16)))
        except Exception:
            continue
        is_default = dest_hex == "00000000"
        try:
            prefix = sum(bin(int(o)).count("1") for o in mask.split("."))
            network = str(ipaddress.IPv4Network(f"{dest}/{prefix}", strict=False))
        except (ValueError, ipaddress.AddressValueError):
            continue
        rows.append(
            {"iface": iface, "network": network, "gateway": gw, "is_default": is_default}
        )
    return rows


def _iface_for_ip(ip: str) -> Optional[str]:
    try:
        addr = ipaddress.IPv4Address(ip)
    except (ValueError, ipaddress.AddressValueError):
        return None
    for r in _parse_proc_net_route():
        if r["is_default"]:
            continue
        try:
            if addr in ipaddress.IPv4Network(r["network"], strict=False):
                return r["iface"]
        except (ValueError, ipaddress.AddressValueError):
            continue
    return None


def discover_lan_subnets() -> List[dict]:
    """Return eligible (iface, network) pairs for an auto-scan."""
    out: List[dict] = []
    for r in _parse_proc_net_route():
        if r["is_default"]:
            continue
        try:
            net = ipaddress.IPv4Network(r["network"], strict=False)
        except (ValueError, ipaddress.AddressValueError):
            continue
        if net.prefixlen >= 31 or net.num_addresses > SCAN_MAX_HOSTS + 2:
            continue
        iface = r["iface"]
        is_docker = _looks_dockerish(iface)
        first = net.network_address
        is_loopback = first.is_loopback
        is_link_local = first.is_link_local
        is_unspecified = str(first).startswith("0.")
        is_eligible = (
            net.is_private
            and not is_loopback
            and not is_link_local
            and not is_unspecified
            and not is_docker
            and not str(net.network_address).startswith("172.")
        )
        if IFACE_ALLOWLIST and iface not in IFACE_ALLOWLIST:
            is_eligible = False
        out.append(
            {
                "iface": iface,
                "network": str(net),
                "is_docker": is_docker,
                "is_loopback": is_loopback,
                "is_link_local": is_link_local,
                "is_unspecified": is_unspecified,
                "is_172": str(net.network_address).startswith("172."),
                "eligible": is_eligible,
            }
        )
    # Deduplicate while preserving order
    seen, dedup = set(), []
    for n in out:
        key = (n["iface"], n["network"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(n)
    return dedup


# ---------------------------------------------------------------------------
# Candidate scanner
# ---------------------------------------------------------------------------

def _classify(buf: bytes) -> dict:
    ais = len(AIS_SENTENCE_RE.findall(buf))
    nmea = len(NMEA_SENTENCE_RE.findall(buf))
    return {
        "is_ais": ais > 0,
        "is_nmea": nmea > 0,
        "ais_count": ais,
        "nmea_count": nmea,
        "bytes": len(buf),
    }


def _probe(ip: str, port: int) -> Optional[dict]:
    """Probe a single (ip, port) and return a candidate dict, or None when closed."""
    sock = None
    candidate = {
        "ip": ip,
        "port": port,
        "status": "closed",
        "score": 0,
        "sample": None,
    }
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SCAN_CONNECT_TIMEOUT)
        try:
            sock.connect((ip, port))
        except (socket.timeout, OSError):
            return None
        sock.settimeout(SCAN_READ_TIMEOUT)
        candidate["status"] = "socket_open"
        candidate["score"] = 25
        # Read a short sample
        deadline = time.time() + SCAN_READ_TIMEOUT
        buf = bytearray()
        while len(buf) < SCAN_READ_BYTES and time.time() < deadline:
            try:
                ready, _, _ = select.select([sock], [], [], 0.5)
                if not ready:
                    break
                chunk = sock.recv(256)
                if not chunk:
                    break
                buf.extend(chunk)
            except (socket.timeout, OSError):
                break
        if buf:
            sample = bytes(buf).decode("latin-1", errors="replace").strip()
            candidate["sample"] = sample[:240]
            candidate["score"] = 45
            info = _classify(bytes(buf))
            if info["is_ais"]:
                candidate["status"] = "ais_detected"
                candidate["score"] = 80 + min(10, info["ais_count"])
            elif info["is_nmea"]:
                candidate["status"] = "nmea_detected"
                candidate["score"] = 65
            else:
                candidate["status"] = "data_received"
        return candidate
    except Exception:
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def scan_for_boat_beacon(subnets: List[str]) -> List[dict]:
    """Scan the given list of CIDRs for AIS/NMEA TCP feeds. Returns sorted candidates."""
    targets: List[Tuple[str, int]] = []
    for cidr in subnets:
        try:
            net = ipaddress.IPv4Network(cidr, strict=False)
        except (ValueError, ipaddress.AddressValueError):
            continue
        for ip in net.hosts():
            for port in SCAN_PORTS:
                targets.append((str(ip), port))
                if len(targets) >= SCAN_MAX_HOSTS * len(SCAN_PORTS):
                    break
            if len(targets) >= SCAN_MAX_HOSTS * len(SCAN_PORTS):
                break
        if len(targets) >= SCAN_MAX_HOSTS * len(SCAN_PORTS):
            break

    log(f"Scanning {len(targets)} targets across {len(subnets)} subnet(s) on ports {SCAN_PORTS}")
    found: List[dict] = []
    with ThreadPoolExecutor(max_workers=SCAN_CONCURRENCY) as pool:
        futures = [pool.submit(_probe, ip, port) for ip, port in targets]
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None and res["status"] != "closed":
                found.append(res)
                if res["status"] in ("ais_detected", "nmea_detected"):
                    log(f"  found {res['ip']}:{res['port']} {res['status']} (score={res['score']})")
    found.sort(key=lambda c: c["score"], reverse=True)
    return found


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _read_cache() -> Optional[dict]:
    try:
        with open(CACHE_PATH, "r") as f:
            data = json.load(f)
            if "ip" in data and "port" in data:
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def _write_cache(ip: str, port: int, source: str, sample: Optional[str]) -> None:
    payload = {
        "ip": ip,
        "port": int(port),
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "last_successful_sample": sample,
    }
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(payload, f, indent=2)
        log(f"Cached Boat Beacon feed to {CACHE_PATH}")
    except OSError as e:
        log(f"WARNING: failed to write cache {CACHE_PATH}: {e}")


def _verify_feed(ip: str, port: int) -> Optional[dict]:
    """Quick verification probe - returns candidate dict if alive."""
    log(f"Verifying Boat Beacon at {ip}:{port}...")
    return _probe(ip, port)


# ---------------------------------------------------------------------------
# Discovery orchestration
# ---------------------------------------------------------------------------

def determine_boat_beacon() -> Optional[dict]:
    """Decide which Boat Beacon endpoint to use. Returns a candidate dict or None."""
    # 1. Explicit env override always wins
    if BOAT_BEACON_IP and BOAT_BEACON_PORT:
        log(f"Using explicit BOAT_BEACON_IP/PORT: {BOAT_BEACON_IP}:{BOAT_BEACON_PORT}")
        return {"ip": BOAT_BEACON_IP, "port": BOAT_BEACON_PORT, "source": "env", "sample": None}

    # 2. Try cache first
    cached = _read_cache()
    if cached:
        log(f"Trying cached Boat Beacon feed: {cached['ip']}:{cached['port']}")
        v = _verify_feed(cached["ip"], int(cached["port"]))
        if v and v["status"] in ("ais_detected", "nmea_detected", "data_received"):
            log(f"  cache hit ({v['status']}, score={v['score']})")
            return {**v, "source": "cache"}
        log("  cached feed unreachable, scanning LAN...")

    # 3. Auto-scan
    if SUBNET_OVERRIDE:
        subnets = [SUBNET_OVERRIDE]
        log(f"Using BOAT_BEACON_SUBNET override: {SUBNET_OVERRIDE}")
    else:
        nets = discover_lan_subnets()
        log("Local interfaces visible:")
        if not nets:
            log("  (none - /proc/net/route empty)")
        for n in nets:
            tags = []
            if n["is_loopback"]:
                tags.append("loopback")
            if n["is_docker"]:
                tags.append("docker")
            if n["is_link_local"]:
                tags.append("link-local")
            if n["is_172"]:
                tags.append("172/12")
            if n["eligible"]:
                tags.append("AUTO-SCAN")
            log(f"  {n['iface']:<10} {n['network']:<20} {' '.join(tags)}")
        subnets = [n["network"] for n in nets if n["eligible"]]

    if not subnets:
        log(
            "No scannable LAN subnet found from this machine. "
            "Provide BOAT_BEACON_SUBNET=192.168.x.0/24 or run on the same network as Boat Beacon."
        )
        return None

    candidates = scan_for_boat_beacon(subnets)
    good = [c for c in candidates if c["status"] in ("ais_detected", "nmea_detected")]
    if not good:
        log("No AIS/NMEA feeds detected during scan.")
        if candidates:
            log(f"  ({len(candidates)} socket_open / data_received result(s) - none matched AIS/NMEA patterns)")
        return None
    pick = good[0]
    log(f"Selected Boat Beacon: {pick['ip']}:{pick['port']} ({pick['status']}, score={pick['score']})")
    return {**pick, "source": "scanner"}


# ---------------------------------------------------------------------------
# Relay loop
# ---------------------------------------------------------------------------

def connect_to_boat_beacon(ip: str, port: int) -> Optional[socket.socket]:
    while running:
        try:
            log(f"Connecting to Boat Beacon at {ip}:{port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((ip, port))
            sock.settimeout(30)
            log("Connected to Boat Beacon!")
            return sock
        except OSError as e:
            log(f"ERROR: Cannot connect to Boat Beacon: {e}")
            stats["errors"] = int(stats["errors"]) + 1  # type: ignore[arg-type]
            log(f"Retrying in {RECONNECT_DELAY} seconds...")
            time.sleep(RECONNECT_DELAY)
    return None


def connect_to_collector() -> Optional[socket.socket]:
    while running:
        try:
            log(f"Connecting to Collector at {COLLECTOR_IP}:{COLLECTOR_PORT}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((COLLECTOR_IP, COLLECTOR_PORT))
            sock.settimeout(None)
            log("Connected to Collector!")
            return sock
        except OSError as e:
            log(f"ERROR: Cannot connect to Collector: {e}")
            stats["errors"] = int(stats["errors"]) + 1  # type: ignore[arg-type]
            log(f"Retrying in {RECONNECT_DELAY} seconds...")
            time.sleep(RECONNECT_DELAY)
    return None


def relay_loop(initial: dict) -> None:
    """Outer relay loop; rescans if Boat Beacon becomes unreachable for too long."""
    global running
    stats["start_time"] = datetime.now()
    feed = initial

    while running:
        boat_beacon_sock = collector_sock = None
        try:
            boat_beacon_sock = connect_to_boat_beacon(feed["ip"], int(feed["port"]))
            if not boat_beacon_sock:
                continue
            collector_sock = connect_to_collector()
            if not collector_sock:
                boat_beacon_sock.close()
                continue

            # Persist the working feed
            _write_cache(feed["ip"], int(feed["port"]), feed.get("source", "scanner"), feed.get("sample"))

            log("Relay active - forwarding NMEA data...")
            buffer = ""
            empty_reads = 0
            while running:
                try:
                    data = boat_beacon_sock.recv(4096)
                    if not data:
                        empty_reads += 1
                        if empty_reads > 3:
                            log("Boat Beacon connection closed")
                            break
                        time.sleep(0.5)
                        continue
                    empty_reads = 0
                    buffer += data.decode("ascii", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            collector_sock.sendall((line + "\n").encode("ascii"))
                            stats["lines_relayed"] = int(stats["lines_relayed"]) + 1  # type: ignore[arg-type]
                            stats["bytes_relayed"] = int(stats["bytes_relayed"]) + len(line)  # type: ignore[arg-type]
                            stats["last_data_time"] = datetime.now()
                            n = int(stats["lines_relayed"])  # type: ignore[arg-type]
                            if n % 100 == 0:
                                log(f"Relayed {n} lines ({stats['bytes_relayed']} bytes)")
                            if n <= 5:
                                log(f"DATA: {line[:80]}...")
                        except OSError as e:
                            log(f"ERROR sending to collector: {e}")
                            stats["errors"] = int(stats["errors"]) + 1  # type: ignore[arg-type]
                            raise
                except socket.timeout:
                    log("WARNING: No data from Boat Beacon for 30 seconds")
                    continue
        except OSError as e:
            log(f"Connection error: {e}")
            stats["errors"] = int(stats["errors"]) + 1  # type: ignore[arg-type]
        finally:
            for s in (boat_beacon_sock, collector_sock):
                if s is not None:
                    try:
                        s.close()
                    except Exception:
                        pass

        if running:
            log(f"Reconnecting in {RECONNECT_DELAY} seconds...")
            time.sleep(RECONNECT_DELAY)


def print_stats() -> None:
    if stats["start_time"]:
        runtime = datetime.now() - stats["start_time"]  # type: ignore[operator]
        log("=== Relay Stats ===")
        log(f"  Runtime: {runtime}")
        log(f"  Lines relayed: {stats['lines_relayed']}")
        log(f"  Bytes relayed: {stats['bytes_relayed']}")
        log(f"  Errors: {stats['errors']}")
        if stats["last_data_time"]:
            log(f"  Last data: {stats['last_data_time']}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log("=" * 60)
    log("River Watch AIS Relay (local sender, auto-discovery)")
    log("=" * 60)
    log(f"Collector: {COLLECTOR_IP}:{COLLECTOR_PORT}")
    log(f"Cache file: {CACHE_PATH}")
    if BOAT_BEACON_IP and BOAT_BEACON_PORT:
        log(f"Boat Beacon: {BOAT_BEACON_IP}:{BOAT_BEACON_PORT} (forced via env)")
    else:
        log("Boat Beacon: auto-discover")
    log("=" * 60)

    feed = determine_boat_beacon()
    if not feed:
        log(
            "No Boat Beacon AIS feed found on reachable local networks. "
            "Confirm Boat Beacon TCP output is enabled and this machine is on the same network."
        )
        log("Hints:")
        log("  - Pass BOAT_BEACON_IP=... BOAT_BEACON_PORT=... if you know the address.")
        log("  - Or BOAT_BEACON_SUBNET=192.168.x.0/24 to force a subnet to scan.")
        log("  - Or IFACE_ALLOWLIST=eth0,wlan0 to restrict which interfaces are used.")
        sys.exit(1)

    try:
        relay_loop(feed)
    except KeyboardInterrupt:
        pass
    finally:
        print_stats()
        log("Relay stopped.")
