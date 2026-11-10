"""Network scanner for the River Watch AIS relay.

Discovers candidate Boat Beacon AIS/NMEA feeds reachable from the relay
container. The scanner:

  1. Enumerates the relay host's local IPv4 subnets (or accepts an
     explicit override like "192.168.1.0/24").
  2. Probes each host on a list of common AIS/NMEA TCP ports.
  3. For each open socket, reads a short sample and scores the
     candidate by socket-open + sample-received + NMEA-sentence
     detected + repeated-messages-received.
  4. Returns sorted candidates with confidence scores.

Designed to be safe to run from inside a Docker container (uses
the standard socket/asyncio APIs - no raw sockets, no ICMP).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import socket
import struct
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("relay.scanner")

# Common ports surfaced by Boat Beacon, OpenCPN, AISdispatcher, kplex,
# AISHub etc. The scanner probes these first.
DEFAULT_PORTS: Tuple[int, ...] = (
    5353, 7000, 10110, 10111, 4001, 4002, 5000, 5001, 8080, 8088,
)

AIS_SENTENCE_RE = re.compile(rb"\!(AIVDM|AIVDO|BSVDM|BSVDO|ABVDM|ABVDO)")
NMEA_SENTENCE_RE = re.compile(rb"\$(GPRMC|GPGGA|GPGLL|GPVTG|GPGSV)")
ANY_NMEA_RE = re.compile(rb"\![A-Z]{5},|\$[A-Z]{5},")

SCAN_TIMEOUT = float(os.environ.get("SCAN_TIMEOUT", "0.6"))
SCAN_READ_BYTES = int(os.environ.get("SCAN_READ_BYTES", "512"))
SCAN_READ_TIMEOUT = float(os.environ.get("SCAN_READ_TIMEOUT", "2.0"))

# Concurrency cap so we don't exhaust the relay host's file descriptors.
MAX_CONCURRENCY = int(os.environ.get("SCAN_CONCURRENCY", "128"))

# Hard cap so a /16 subnet override doesn't fork 65k probes by accident.
MAX_HOSTS = int(os.environ.get("SCAN_MAX_HOSTS", "512"))

# Interfaces created by Docker / k8s / VPN tooling. We want to *see* them
# (for diagnostics) but never auto-scan them.
DOCKER_IFACE_PREFIXES = (
    "docker", "br-", "veth", "cni", "flannel", "weave", "cali", "tun", "tap", "vxlan",
)


def _classify_iface(iface: str) -> dict:
    is_loopback = iface == "lo" or iface.startswith("lo:")
    is_docker = any(iface.startswith(p) for p in DOCKER_IFACE_PREFIXES)
    return {"is_loopback": is_loopback, "is_docker": is_docker}


def _classify_ip(ip: str) -> dict:
    try:
        addr = ipaddress.IPv4Address(ip)
    except (ValueError, ipaddress.AddressValueError):
        return {"is_loopback": False, "is_link_local": False, "is_private": False,
                "is_reserved": True, "is_172_block": False}
    return {
        "is_loopback": addr.is_loopback,
        "is_link_local": addr.is_link_local,
        "is_private": addr.is_private and not addr.is_loopback and not addr.is_link_local,
        "is_reserved": addr.is_reserved or addr.is_multicast or addr.is_unspecified,
        "is_172_block": ip.startswith("172."),
    }


def _parse_proc_net_route() -> List[dict]:
    """
    Parse /proc/net/route and return one entry per interface that owns a
    real route (i.e. has a non-zero destination *or* is the default route).

    Each entry: {iface, network (CIDR), netmask, gateway, is_default}
    """
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
        is_default = (dest_hex == "00000000")
        try:
            prefix = sum(bin(int(o)).count("1") for o in mask.split("."))
            network = str(ipaddress.IPv4Network(f"{dest}/{prefix}", strict=False))
        except (ValueError, ipaddress.AddressValueError):
            continue
        rows.append({
            "iface": iface,
            "network": network,
            "netmask": mask,
            "gateway": gw,
            "is_default": is_default,
        })
    return rows


def _ips_per_iface() -> Dict[str, List[str]]:
    """Map iface name -> list of assigned IPv4 addresses from /proc/net/fib_trie."""
    out: Dict[str, List[str]] = {}
    try:
        with open("/proc/net/fib_trie", "r") as f:
            data = f.read()
    except FileNotFoundError:
        return out
    # fib_trie has alternating sections per table. Local IPs live under
    # entries marked "LOCAL"; we just want every IP marked as host-local
    # whatever interface it's attached to, then we'll cross-reference
    # against route destinations.
    # The structure doesn't list iface inline, so we use ifaddrs via
    # /sys/class/net/*/address to discover interfaces and ip-link bind
    # via socket if available. As a portable fallback we just gather
    # all local IPs and let route entries provide the iface mapping.
    ips: List[str] = []
    for line in data.splitlines():
        m = re.search(r"\|--\s+([0-9.]+)$", line.strip())
        if m:
            ips.append(m.group(1))
    # Assign each IP to whichever iface owns its /24 (best effort).
    routes = _parse_proc_net_route()
    for ip in ips:
        try:
            addr = ipaddress.IPv4Address(ip)
        except (ValueError, ipaddress.AddressValueError):
            continue
        chosen = "?"
        for r in routes:
            if r["is_default"]:
                continue
            try:
                if addr in ipaddress.IPv4Network(r["network"], strict=False):
                    chosen = r["iface"]
                    break
            except (ValueError, ipaddress.AddressValueError):
                continue
        out.setdefault(chosen, []).append(ip)
    return out


def list_visible_networks() -> List[dict]:
    """
    Return the relay's visible IPv4 networks with classification flags so
    the UI can show what the scanner can / cannot see.

    Eligibility for auto-scan:
      - Must be IPv4 private RFC1918 space
      - Must NOT be loopback, link-local, multicast or reserved
      - Interface name must NOT match a Docker/VPN bridge prefix
      - 172.16/12 ranges are NEVER auto-scanned (operator must opt in
        explicitly via the subnet override).
    """
    routes = _parse_proc_net_route()
    iface_ips = _ips_per_iface()

    seen: Dict[str, dict] = {}
    for r in routes:
        if r["is_default"]:
            continue
        net = r["network"]
        iface = r["iface"]
        iface_flags = _classify_iface(iface)
        try:
            netobj = ipaddress.IPv4Network(net, strict=False)
        except (ValueError, ipaddress.AddressValueError):
            continue
        # Skip /32 host routes
        if netobj.prefixlen >= 31:
            continue
        ip_for_iface = (iface_ips.get(iface) or [None])[0]
        flags = _classify_ip(ip_for_iface or str(netobj.network_address))
        is_eligible_auto = (
            flags["is_private"]
            and not iface_flags["is_loopback"]
            and not iface_flags["is_docker"]
            and not flags["is_172_block"]   # opt-in only
            and netobj.num_addresses <= MAX_HOSTS + 2
        )
        entry = {
            "iface": iface,
            "network": net,
            "ip": ip_for_iface,
            "is_loopback": iface_flags["is_loopback"] or flags["is_loopback"],
            "is_docker": iface_flags["is_docker"],
            "is_link_local": flags["is_link_local"],
            "is_172_block": flags["is_172_block"],
            "is_private": flags["is_private"],
            "eligible_for_auto_scan": is_eligible_auto,
        }
        # Deduplicate (multiple route rows for same network)
        key = f"{iface}:{net}"
        if key not in seen:
            seen[key] = entry
    return list(seen.values())


def detect_local_subnets() -> List[str]:
    """Return only the subnets eligible for an unattended auto-scan."""
    nets = list_visible_networks()
    return [n["network"] for n in nets if n["eligible_for_auto_scan"]]


class NoUsableSubnetError(RuntimeError):
    """Raised by run_scan when auto-detection finds nothing scannable."""


def resolve_targets(subnet_override: Optional[str], ports: Iterable[int]) -> Tuple[List[Tuple[str, int]], str]:
    """Return list of (ip, port) tuples to probe and the human-readable subnet label."""
    ports = list(ports) if ports else list(DEFAULT_PORTS)
    if subnet_override:
        try:
            net = ipaddress.ip_network(subnet_override, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid subnet '{subnet_override}': {e}")
        if net.version != 4:
            raise ValueError("Only IPv4 subnets are supported")
        subnets = [str(net)]
    else:
        subnets = detect_local_subnets()
        if not subnets:
            raise NoUsableSubnetError(
                "No scannable LAN subnet found from this relay. "
                "Run the relay on the same network as Boat Beacon "
                "or provide a reachable subnet manually."
            )

    hosts: List[str] = []
    for s in subnets:
        net = ipaddress.IPv4Network(s, strict=False)
        # `.hosts()` excludes network + broadcast addresses
        for ip in net.hosts():
            hosts.append(str(ip))
            if len(hosts) >= MAX_HOSTS:
                break
        if len(hosts) >= MAX_HOSTS:
            break

    targets = [(h, p) for h in hosts for p in ports]
    return targets, ",".join(subnets)


def _classify_sample(buf: bytes) -> dict:
    """Return scoring metadata for a sampled byte buffer."""
    info = {
        "ais_count": len(AIS_SENTENCE_RE.findall(buf)),
        "nmea_count": len(NMEA_SENTENCE_RE.findall(buf)),
        "any_nmea_count": len(ANY_NMEA_RE.findall(buf)),
        "bytes": len(buf),
    }
    info["is_ais"] = info["ais_count"] > 0
    info["is_nmea"] = info["nmea_count"] > 0 or info["any_nmea_count"] > 0
    return info


async def _probe_one(ip: str, port: int, sem: asyncio.Semaphore) -> Optional[dict]:
    """Probe a single (ip, port). Returns a candidate dict or None when closed."""
    async with sem:
        reader = writer = None
        candidate = {
            "ip": ip,
            "port": port,
            "status": "closed",
            "score": 0,
            "sample": None,
            "last_seen": None,
            "error": None,
            "details": {},
        }
        try:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port), timeout=SCAN_TIMEOUT
                )
            except (asyncio.TimeoutError, OSError) as e:
                # Filter out the common "Connection refused" / timeout to keep noise low
                candidate["error"] = type(e).__name__
                return None
            candidate["status"] = "socket_open"
            candidate["score"] = 25

            buf = bytearray()
            deadline = asyncio.get_event_loop().time() + SCAN_READ_TIMEOUT
            while len(buf) < SCAN_READ_BYTES:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    chunk = await asyncio.wait_for(reader.read(256), timeout=min(remaining, 1.0))
                except asyncio.TimeoutError:
                    break
                if not chunk:
                    break
                buf.extend(chunk)
            if buf:
                sample_text = buf.decode("latin-1", errors="replace").strip()
                candidate["sample"] = sample_text[:240]
                candidate["score"] = 45
                info = _classify_sample(bytes(buf))
                candidate["details"] = info
                if info["is_ais"]:
                    candidate["status"] = "ais_detected"
                    base = 80
                    base += min(10, info["ais_count"])  # repetition bonus
                    candidate["score"] = base
                elif info["is_nmea"]:
                    candidate["status"] = "nmea_detected"
                    candidate["score"] = 65
                else:
                    candidate["status"] = "data_received"
                candidate["last_seen"] = datetime.now(timezone.utc).isoformat()
            return candidate
        except Exception as e:
            candidate["error"] = f"{type(e).__name__}: {e}"
            return candidate
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass


async def run_scan(
    subnet_override: Optional[str],
    ports: Optional[Iterable[int]],
    progress_cb=None,
) -> Tuple[List[dict], str]:
    """Run the scan and return (candidates_sorted_desc, subnet_label)."""
    targets, subnet_label = resolve_targets(subnet_override, ports or DEFAULT_PORTS)
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    coros = [_probe_one(ip, port, sem) for ip, port in targets]

    candidates: List[dict] = []
    done = 0
    total = len(coros)
    if progress_cb:
        progress_cb(0, total)
    for fut in asyncio.as_completed(coros):
        res = await fut
        done += 1
        if res is not None and res["status"] != "closed":
            candidates.append(res)
        if progress_cb and (done % max(1, total // 20) == 0 or done == total):
            progress_cb(done, total)

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates, subnet_label


def filter_results(
    results: List[dict],
    *,
    include_low_confidence: bool = False,
    exclude_loopback: bool = True,
    exclude_docker: bool = True,
) -> List[dict]:
    """
    Apply the result filters requested by the audit:
      - exclude loopback (127.0.0.0/8) by default
      - exclude Docker bridge ranges (172.17/16, 172.18/16, ...) by default
      - hide socket_open-only noise unless include_low_confidence=True

    A candidate counts as 'high confidence' if any of:
      * AIS sentence detected
      * NMEA sentence detected
      * a non-empty sample was received
    """
    docker_nets = [ipaddress.IPv4Network(f"172.{n}.0.0/16") for n in range(17, 32)]

    def keep(c: dict) -> bool:
        try:
            addr = ipaddress.IPv4Address(c.get("ip", ""))
        except (ValueError, ipaddress.AddressValueError):
            return False
        if exclude_loopback and addr.is_loopback:
            return False
        if exclude_loopback and addr.is_link_local:
            return False
        if exclude_docker and any(addr in n for n in docker_nets):
            return False
        if not include_low_confidence:
            details = c.get("details") or {}
            high = bool(details.get("is_ais")) or bool(details.get("is_nmea")) or bool(c.get("sample"))
            if not high:
                return False
        return True

    return [c for c in results if keep(c)]

