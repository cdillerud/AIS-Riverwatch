#!/usr/bin/env python3
"""
AIS Relay (HTTP-POST mode)
==========================

Connects to Boat Beacon's NMEA TCP server on your LAN and POSTs the raw
lines to the River Watch VM over plain HTTPS. No router port-forward,
no static IP, no TCP listener on the VM — just outbound HTTPS.

Run this on ANY machine that:
  - is on the same Wi-Fi as Boat Beacon (so it can reach 192.168.0.25:5353)
  - has internet access (so it can reach the VM over HTTPS)

Usage:
    python3 ais_relay.py

Configure via env vars (all optional, defaults shown):
    BOAT_BEACON_IP=192.168.0.25
    BOAT_BEACON_PORT=5353
    VM_URL=https://mississippi-kiosk.preview.emergentagent.com
    USER_MMSI=                       # your vessel's MMSI (required for GPS to be attributed)
    BOAT_NAME=                       # your vessel's display name (optional)
    BATCH_SECONDS=1.0                # how often to flush to the VM
    MAX_BATCH_LINES=200              # cap per POST
"""

import os
import sys
import time
import socket
import signal
import threading
from datetime import datetime
from urllib import request as urlrequest
from urllib import error as urlerror
import json

# ----- Configuration -----------------------------------------------------------
BOAT_BEACON_IP   = os.environ.get("BOAT_BEACON_IP", "192.168.0.25")
BOAT_BEACON_PORT = int(os.environ.get("BOAT_BEACON_PORT", "5353"))
VM_URL           = os.environ.get("VM_URL", "http://136.116.165.255:8001").rstrip("/")
USER_MMSI        = os.environ.get("USER_MMSI", "")
BOAT_NAME        = os.environ.get("BOAT_NAME", "")
BATCH_SECONDS    = float(os.environ.get("BATCH_SECONDS", "1.0"))
MAX_BATCH_LINES  = int(os.environ.get("MAX_BATCH_LINES", "200"))
RECONNECT_DELAY  = 5     # seconds between Boat Beacon reconnect attempts

INGEST_URL = f"{VM_URL}/api/ais/ingest"

# ----- State -------------------------------------------------------------------
_lines_lock = threading.Lock()
_pending_lines: list[str] = []
running = True
stats = {
    "lines_read": 0,
    "batches_sent": 0,
    "lines_sent": 0,
    "errors": 0,
    "last_data_time": None,
    "last_post_time": None,
    "start_time": None,
}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _shutdown(*_):
    global running
    log("Shutting down…")
    running = False


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ----- Reader: pulls lines from Boat Beacon -----------------------------------
def reader_loop():
    """Connect to Boat Beacon TCP and append every NMEA line to the buffer."""
    global running
    while running:
        sock = None
        try:
            log(f"Connecting to Boat Beacon @ {BOAT_BEACON_IP}:{BOAT_BEACON_PORT} …")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((BOAT_BEACON_IP, BOAT_BEACON_PORT))
            sock.settimeout(30)
            log("Boat Beacon connected. Streaming NMEA…")

            buf = ""
            while running:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    log("No data from Boat Beacon for 30s — still waiting…")
                    continue
                if not chunk:
                    log("Boat Beacon closed the connection.")
                    break
                buf += chunk.decode("ascii", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    with _lines_lock:
                        _pending_lines.append(line)
                        stats["lines_read"] += 1
                        stats["last_data_time"] = datetime.now()
                        if stats["lines_read"] <= 5:
                            log(f"NMEA: {line[:90]}")
                        elif stats["lines_read"] % 200 == 0:
                            log(f"Read {stats['lines_read']} lines so far")
        except Exception as e:
            stats["errors"] += 1
            log(f"Boat Beacon error: {e}")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

        if running:
            log(f"Reconnecting to Boat Beacon in {RECONNECT_DELAY}s…")
            time.sleep(RECONNECT_DELAY)


# ----- Sender: flushes the buffer to the VM over HTTPS ------------------------
def _post_batch(lines: list[str]) -> bool:
    body = json.dumps({
        "user_mmsi": USER_MMSI,
        "boat_name": BOAT_NAME,
        "lines": lines,
    }).encode("utf-8")
    req = urlrequest.Request(
        INGEST_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            payload = resp.read(2048).decode("utf-8", errors="ignore")
            if resp.status == 200:
                if stats["batches_sent"] < 3 or stats["batches_sent"] % 60 == 0:
                    log(f"POST {INGEST_URL} → 200 ({len(lines)} lines) {payload[:120]}")
                return True
            log(f"POST {INGEST_URL} → HTTP {resp.status}: {payload[:200]}")
            return False
    except urlerror.HTTPError as e:
        log(f"HTTPError {e.code} from VM: {e.read()[:200] if e.fp else ''}")
    except urlerror.URLError as e:
        log(f"Cannot reach VM: {e.reason}")
    except Exception as e:
        log(f"POST failed: {e}")
    return False


def sender_loop():
    """Every BATCH_SECONDS, drain pending lines and POST them to the VM."""
    while running:
        time.sleep(BATCH_SECONDS)
        with _lines_lock:
            if not _pending_lines:
                continue
            batch = _pending_lines[:MAX_BATCH_LINES]
            del _pending_lines[: len(batch)]

        ok = _post_batch(batch)
        if ok:
            stats["batches_sent"] += 1
            stats["lines_sent"] += len(batch)
            stats["last_post_time"] = datetime.now()
        else:
            stats["errors"] += 1
            # Put the batch back at the front so we don't lose data
            with _lines_lock:
                _pending_lines[:0] = batch
            # Brief back-off so we don't hammer a broken VM
            time.sleep(2)


def main():
    log("=" * 56)
    log("AIS NMEA Relay → HTTP POST")
    log("=" * 56)
    log(f"  Boat Beacon : {BOAT_BEACON_IP}:{BOAT_BEACON_PORT}")
    log(f"  VM ingest   : {INGEST_URL}")
    log(f"  USER_MMSI   : {USER_MMSI or '(unset – set USER_MMSI for GPS attribution)'}")
    log(f"  BOAT_NAME   : {BOAT_NAME or '(unset)'}")
    log(f"  Batch       : every {BATCH_SECONDS}s, up to {MAX_BATCH_LINES} lines")
    log("=" * 56)
    log("Press Ctrl+C to stop.")
    log("")

    stats["start_time"] = datetime.now()
    t_reader = threading.Thread(target=reader_loop, daemon=True, name="reader")
    t_sender = threading.Thread(target=sender_loop, daemon=True, name="sender")
    t_reader.start()
    t_sender.start()

    try:
        while running:
            time.sleep(15)
            uptime = datetime.now() - stats["start_time"]
            last_data = stats["last_data_time"].strftime("%H:%M:%S") if stats["last_data_time"] else "—"
            last_post = stats["last_post_time"].strftime("%H:%M:%S") if stats["last_post_time"] else "—"
            log(
                f"status uptime={uptime} read={stats['lines_read']} "
                f"sent={stats['lines_sent']} batches={stats['batches_sent']} "
                f"errors={stats['errors']} last_nmea={last_data} last_post={last_post}"
            )
    except KeyboardInterrupt:
        pass
    finally:
        log("Relay stopped.")


if __name__ == "__main__":
    sys.exit(main())
