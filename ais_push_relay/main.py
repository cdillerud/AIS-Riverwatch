"""River Watch AIS push relay - main entrypoint.

Runs two listeners concurrently:

  - HTTP API (uvicorn) on ${WS_HOST}:${WS_PORT} for scanner + selection
  - TCP NMEA fanout on ${TCP_HOST}:${TCP_PORT} for the backend container
    (backend AISConnectionManager opens a raw TCP socket to this port and
    expects to receive NMEA sentences).

The relay's job is to open a TCP client connection to the currently
selected Boat Beacon upstream feed, buffer the lines, and broadcast each
line byte-for-byte to every TCP client currently connected to its fanout
port. When the operator selects a new feed via POST /scan/select, the
upstream socket is dropped and reopened against the new target.

If no feed is selected the relay sits idle (clients on :5353 simply
receive no data) and /scan/status reports the empty selection.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
import uvicorn

import state
import scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("relay")

WS_HOST = os.environ.get("WS_HOST", "0.0.0.0")
WS_PORT = int(os.environ.get("WS_PORT", "8088"))
TCP_HOST = os.environ.get("TCP_HOST", "0.0.0.0")
TCP_PORT = int(os.environ.get("TCP_PORT", "5353"))
# Legacy push-ingest TCP port. scripts/ais_relay.py and other local
# senders open a TCP connection here and write newline-delimited NMEA.
INGEST_HOST = os.environ.get("INGEST_HOST", "0.0.0.0")
INGEST_PORT = int(os.environ.get("INGEST_PORT", "6000"))
INGEST_IDLE_TIMEOUT = float(os.environ.get("INGEST_IDLE_TIMEOUT", "120"))
INGEST_TOKEN = os.environ.get("AIS_RELAY_TOKEN", "").strip() or None

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

fanout_clients: Set[asyncio.StreamWriter] = set()
fanout_lock = asyncio.Lock()
upstream_task: Optional[asyncio.Task] = None
upstream_stop_event: Optional[asyncio.Event] = None
scan_task: Optional[asyncio.Task] = None
scan_lock = asyncio.Lock()

# Push-ingest stats (mirrors the upstream block but for inbound pushers)
push_stats: Dict[str, object] = {
    "lines_received": 0,
    "last_line_at": None,
    "last_client": None,
    "current_clients": 0,
    "last_error": None,
}


# ---------------------------------------------------------------------------
# Upstream Boat Beacon TCP client
# ---------------------------------------------------------------------------

async def _broadcast(line: bytes) -> None:
    async with fanout_lock:
        dead = []
        for w in fanout_clients:
            try:
                w.write(line)
                await w.drain()
            except Exception:
                dead.append(w)
        for w in dead:
            fanout_clients.discard(w)
            try:
                w.close()
            except Exception:
                pass


async def upstream_loop(ip: str, port: int, stop_event: asyncio.Event) -> None:
    """Persistent TCP client to the Boat Beacon feed. Reconnects with backoff."""
    logger.info("[upstream] target=%s:%s starting", ip, port)
    backoff = 1.0
    while not stop_event.is_set():
        reader = writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=8.0)
            state.update_upstream(
                connected=True,
                last_connect_at=datetime.now(timezone.utc).isoformat(),
                last_error=None,
                selected_ip=ip,
                selected_port=port,
            )
            logger.info("[upstream] connected to %s:%s", ip, port)
            backoff = 1.0
            while not stop_event.is_set():
                line = await reader.readline()
                if not line:
                    raise ConnectionError("upstream closed")
                state.update_upstream(
                    last_line_at=datetime.now(timezone.utc).isoformat(),
                    lines_received=state.snapshot()["upstream"]["lines_received"] + 1,
                )
                await _broadcast(line)
        except Exception as e:
            state.update_upstream(connected=False, last_error=f"{type(e).__name__}: {e}")
            logger.warning("[upstream] %s:%s error: %s", ip, port, e)
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
        if stop_event.is_set():
            break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            break
        except asyncio.TimeoutError:
            pass
        backoff = min(30.0, backoff * 1.6)
    state.update_upstream(connected=False, selected_ip=None, selected_port=None)
    logger.info("[upstream] target=%s:%s stopped", ip, port)


async def start_upstream(ip: str, port: int) -> None:
    global upstream_task, upstream_stop_event
    await stop_upstream()
    upstream_stop_event = asyncio.Event()
    upstream_task = asyncio.create_task(upstream_loop(ip, port, upstream_stop_event))


async def stop_upstream() -> None:
    global upstream_task, upstream_stop_event
    if upstream_stop_event:
        upstream_stop_event.set()
    if upstream_task and not upstream_task.done():
        try:
            await asyncio.wait_for(upstream_task, timeout=5.0)
        except Exception:
            pass
    upstream_task = None
    upstream_stop_event = None


# ---------------------------------------------------------------------------
# TCP fanout server (backend connects here)
# ---------------------------------------------------------------------------

async def _handle_fanout_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    logger.info("[fanout] client connected from %s", peer)
    async with fanout_lock:
        fanout_clients.add(writer)
    try:
        while not writer.is_closing():
            try:
                # Read anything to detect disconnect; ignore content.
                data = await asyncio.wait_for(reader.read(1024), timeout=30.0)
            except asyncio.TimeoutError:
                continue
            if not data:
                break
    except Exception as e:
        logger.warning("[fanout] client %s error: %s", peer, e)
    finally:
        async with fanout_lock:
            fanout_clients.discard(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        logger.info("[fanout] client disconnected from %s", peer)


async def start_fanout_server() -> asyncio.AbstractServer:
    server = await asyncio.start_server(_handle_fanout_client, TCP_HOST, TCP_PORT)
    logger.info("[fanout] listening on %s:%s", TCP_HOST, TCP_PORT)
    return server


# ---------------------------------------------------------------------------
# Push-ingest TCP server (legacy local senders connect here on :6000)
# ---------------------------------------------------------------------------

async def _ingest_record_line(line: bytes, peer: object) -> None:
    push_stats["lines_received"] = int(push_stats["lines_received"]) + 1  # type: ignore[arg-type]
    push_stats["last_line_at"] = datetime.now(timezone.utc).isoformat()
    push_stats["last_client"] = str(peer)
    await _broadcast(line if line.endswith(b"\n") else line + b"\n")


async def _handle_ingest_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    logger.info("[ingest-tcp] sender connected from %s", peer)
    push_stats["current_clients"] = int(push_stats["current_clients"]) + 1  # type: ignore[arg-type]
    try:
        while True:
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=INGEST_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("[ingest-tcp] idle timeout from %s, closing", peer)
                break
            if not line:
                break
            await _ingest_record_line(line, peer)
    except Exception as e:
        logger.warning("[ingest-tcp] sender %s error: %s", peer, e)
        push_stats["last_error"] = f"{type(e).__name__}: {e}"
    finally:
        push_stats["current_clients"] = max(0, int(push_stats["current_clients"]) - 1)  # type: ignore[arg-type]
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        logger.info("[ingest-tcp] sender %s disconnected", peer)


async def start_ingest_server() -> asyncio.AbstractServer:
    server = await asyncio.start_server(_handle_ingest_client, INGEST_HOST, INGEST_PORT)
    logger.info(
        "[ingest-tcp] listening on %s:%s (legacy push, token=%s)",
        INGEST_HOST,
        INGEST_PORT,
        "set" if INGEST_TOKEN else "unset",
    )
    return server


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    subnet: Optional[str] = Field(None, description="Optional CIDR override, e.g. 192.168.1.0/24")
    ports: Optional[list] = Field(None, description="Optional explicit port list")


class SelectRequest(BaseModel):
    ip: str
    port: int


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    fanout_server = await start_fanout_server()
    ingest_server = await start_ingest_server()
    # If a feed was previously selected, resume its upstream client.
    sel = state.get_selected_feed()
    if sel:
        await start_upstream(sel["selected_ip"], int(sel["selected_port"]))
    try:
        yield
    finally:
        await stop_upstream()
        for srv in (fanout_server, ingest_server):
            srv.close()
            try:
                await srv.wait_closed()
            except Exception:
                pass


app = FastAPI(title="River Watch AIS Push Relay", version="1.1", lifespan=lifespan)


def _current_mode() -> str:
    if int(push_stats["current_clients"]) > 0 or push_stats["last_line_at"]:  # type: ignore[arg-type]
        return "push"
    if state.get_selected_feed() and state.snapshot()["upstream"].get("connected"):
        return "pull"
    return "idle"


@app.get("/health")
async def health():
    snap = state.snapshot()
    return {
        "status": "ok",
        "mode": _current_mode(),
        "push_ingest": {
            "lines_received": push_stats["lines_received"],
            "last_line_at": push_stats["last_line_at"],
            "last_client": push_stats["last_client"],
            "current_clients": push_stats["current_clients"],
            "ingest_tcp": f"{INGEST_HOST}:{INGEST_PORT}",
            "token_required": INGEST_TOKEN is not None,
            "last_error": push_stats["last_error"],
        },
        "upstream": snap["upstream"],
        "fanout_clients": len(fanout_clients),
        "selected_feed": snap["selected_feed"],
        "scan_status": snap["scan_status"]["state"],
    }


# --- HTTP ingest (new, optional) ------------------------------------------

class HTTPIngestPayload(BaseModel):
    lines: Optional[list] = None
    text: Optional[str] = None


@app.post("/ingest/nmea")
async def http_ingest(
    payload: HTTPIngestPayload,
    x_relay_token: Optional[str] = Header(default=None, alias="X-Relay-Token"),
):
    """
    HTTP push endpoint for senders that prefer JSON over a raw TCP socket.
    Body shape (any of):
        {"lines": ["!AIVDM,1,...", "$GPRMC,...", ...]}
        {"text": "!AIVDM,...\\n$GPRMC,..."}

    Auth: when AIS_RELAY_TOKEN is set, callers must include X-Relay-Token
    header. When unset the endpoint accepts unauthenticated pushes (LAN-only
    use case).
    """
    if INGEST_TOKEN and x_relay_token != INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid relay token")
    lines: list = []
    if payload.lines:
        lines.extend([str(line) for line in payload.lines])
    if payload.text:
        lines.extend([line for line in payload.text.splitlines() if line.strip()])
    if not lines:
        raise HTTPException(status_code=400, detail="No NMEA lines supplied")
    for line in lines:
        await _ingest_record_line(line.encode("ascii", errors="ignore"), "http-ingest")
    return {"status": "ok", "lines_accepted": len(lines)}


@app.get("/scan/status")
async def scan_status():
    snap = state.snapshot()
    networks = scanner.list_visible_networks()
    has_usable = any(n["eligible_for_auto_scan"] for n in networks)
    return {
        "scan_status": snap["scan_status"],
        "last_scan": snap["last_scan"],
        "selected_feed": snap["selected_feed"],
        "upstream": snap["upstream"],
        "fanout_clients": len(fanout_clients),
        "networks": networks,
        "auto_scan_supported": has_usable,
        "auto_scan_hint": (
            None if has_usable
            else "Relay only sees Docker/loopback interfaces. Provide a subnet override or run the relay on the same LAN as Boat Beacon."
        ),
        "mode": _current_mode(),
        "push_ingest": {
            "lines_received": push_stats["lines_received"],
            "last_line_at": push_stats["last_line_at"],
            "last_client": push_stats["last_client"],
            "current_clients": push_stats["current_clients"],
            "ingest_tcp": f"{INGEST_HOST}:{INGEST_PORT}",
            "token_required": INGEST_TOKEN is not None,
            "last_error": push_stats["last_error"],
        },
    }


@app.post("/scan/boat-beacon")
async def trigger_boat_beacon_scan(req: ScanRequest):
    """Kick off a network scan for Boat Beacon AIS feeds."""
    global scan_task
    # Reject auto scan early if there's nothing scannable - much faster
    # than queuing 65k probes against the docker bridge.
    if not req.subnet:
        try:
            scanner.resolve_targets(None, scanner.DEFAULT_PORTS)
        except scanner.NoUsableSubnetError as e:
            state.update_scan_status(
                state="completed",
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
                progress=0.0,
                scanned=0,
                total=0,
                subnet=None,
                error=str(e),
            )
            return {"status": "no_usable_subnet", "error": str(e)}
    async with scan_lock:
        if scan_task and not scan_task.done():
            raise HTTPException(status_code=409, detail="A scan is already running")
        state.update_scan_status(
            state="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            progress=0.0,
            scanned=0,
            total=0,
            subnet=req.subnet,
            error=None,
        )
        scan_task = asyncio.create_task(_run_scan_task(req.subnet, req.ports))
    return {"status": "scan_started", "subnet": req.subnet}


async def _run_scan_task(subnet: Optional[str], ports: Optional[list]) -> None:
    def progress(done: int, total: int) -> None:
        state.update_scan_status(
            scanned=done,
            total=total,
            progress=(done / total) if total else 0.0,
        )

    try:
        candidates, subnet_label = await scanner.run_scan(subnet, ports, progress_cb=progress)
        state.set_scan_results(candidates, subnet=subnet_label)
        state.update_scan_status(
            state="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            progress=1.0,
            subnet=subnet_label,
            error=None,
        )
        logger.info("[scanner] completed with %d candidates on %s", len(candidates), subnet_label)
    except scanner.NoUsableSubnetError as e:
        logger.info("[scanner] no usable subnet: %s", e)
        state.set_scan_results([], subnet=None)
        state.update_scan_status(
            state="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            progress=0.0,
            subnet=None,
            error=str(e),
        )
    except Exception as e:
        logger.exception("[scanner] scan failed")
        state.update_scan_status(
            state="error",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error=f"{type(e).__name__}: {e}",
        )


@app.get("/scan/results")
async def scan_results(
    include_low_confidence: bool = False,
    exclude_loopback: bool = True,
    exclude_docker: bool = True,
):
    """List of candidates from the most recent scan, filtered to high
    confidence by default (AIS / NMEA / sample received).

    Set include_low_confidence=true to also see socket_open-only rows."""
    snap = state.snapshot()
    raw_results = snap["scan_results"]
    filtered = scanner.filter_results(
        raw_results,
        include_low_confidence=include_low_confidence,
        exclude_loopback=exclude_loopback,
        exclude_docker=exclude_docker,
    )
    return {
        "results": filtered,
        "raw_count": len(raw_results),
        "shown_count": len(filtered),
        "filters": {
            "include_low_confidence": include_low_confidence,
            "exclude_loopback": exclude_loopback,
            "exclude_docker": exclude_docker,
        },
        "last_scan": snap["last_scan"],
        "scan_status": snap["scan_status"],
    }


@app.post("/scan/select")
async def scan_select(req: SelectRequest):
    if not req.ip or not (1 <= req.port <= 65535):
        raise HTTPException(status_code=400, detail="Invalid ip/port")
    # Find the matching candidate (if any) so we can persist its sample.
    sample = None
    for c in state.snapshot()["scan_results"]:
        if c.get("ip") == req.ip and int(c.get("port", 0)) == int(req.port):
            sample = c.get("sample")
            break
    feed = state.set_selected_feed(req.ip, int(req.port), sample)
    await start_upstream(req.ip, int(req.port))
    return {"status": "selected", "selected_feed": feed}


@app.post("/scan/clear")
async def scan_clear():
    state.clear_selected_feed()
    await stop_upstream()
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(stop_upstream()))
        except NotImplementedError:
            pass


if __name__ == "__main__":
    uvicorn.run("main:app", host=WS_HOST, port=WS_PORT, log_level="info")
