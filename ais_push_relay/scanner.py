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
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

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


def _is_private_v4(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.version == 4 and (addr.is_private or addr.is_link_local)
    except ValueError:
        return False


def detect_local_subnets() -> List[str]:
    """
    Best-effort detection of the relay host's local IPv4 /24 subnets.

    We avoid raw netlink/route lookups (which require CAP_NET_ADMIN inside
    containers) and instead:
      - Try /proc/net/fib_trie for assigned local IPs (Linux-only).
      - Fall back to socket.getaddrinfo on the host name.
      - Always derive a /24 from each discovered private IP.
    """
    found: List[str] = []
    seen = set()

    def add(ip: str) -> None:
        if _is_private_v4(ip):
            net = str(ipaddress.IPv4Network(f"{ip}/24", strict=False))
            if net not in seen:
                seen.add(net)
                found.append(net)

    try:
        with open("/proc/net/fib_trie", "r") as f:
            data = f.read()
        # Lines containing assigned local IPs look like:
        #   |-- 192.168.1.42 ... LOCAL ... host
        for line in data.splitlines():
            m = re.search(r"\|--\s+([0-9.]+)$", line.strip())
            if m:
                add(m.group(1))
    except Exception as e:
        logger.debug(f"[scanner] /proc/net/fib_trie unavailable: {e}")

    try:
        hostname = socket.gethostname()
        for fam, _, _, _, sa in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            if fam == socket.AF_INET:
                add(sa[0])
    except Exception as e:
        logger.debug(f"[scanner] getaddrinfo({socket.gethostname()}) failed: {e}")

    # Always include the docker bridge fallback so the scanner finds *something*
    # when running inside a stock compose network.
    add("172.17.0.1")

    return found


def resolve_targets(subnet_override: Optional[str], ports: Iterable[int]) -> Tuple[List[Tuple[str, int]], str]:
    """Return list of (ip, port) tuples to probe and the human-readable subnet label."""
    ports = list(ports) or list(DEFAULT_PORTS)
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
            raise RuntimeError("Could not detect a local subnet; pass subnet=<cidr> override")

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
