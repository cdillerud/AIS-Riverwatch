"""A pending reconnect must not tear down a healthy AIS connection (2 s flap loop)."""
import asyncio

import server

LINE = b"!AIVDM,1,1,,A,102>hgAP00OkeS6MV3<h005p0000,0*28\r\n"


async def _run_scenario():
    accepted = []

    async def phone(reader, writer):  # streams forever, like the phone app
        accepted.append(writer)
        try:
            while True:
                writer.write(LINE)
                await writer.drain()
                await asyncio.sleep(0.05)
        except (ConnectionError, asyncio.CancelledError):
            pass

    srv = await asyncio.start_server(phone, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    mgr = server.AISConnectionManager()
    mgr._broadcast_status = _noop
    mgr._process_line = _noop
    try:
        mgr._config = {"ip_address": "127.0.0.1", "port": port, "user_mmsi": "", "boat_name": ""}
        mgr._should_run = True
        mgr._reconnect_delay = 0.2
        # A retry was pending (feed had been down)...
        await mgr._schedule_reconnect()
        # ...and then something else reconnected first (Settings / manual reconnect).
        await mgr._connect()
        await asyncio.sleep(1.5)  # pending retry fires; with the bug this flaps
        return len(accepted), mgr._connected
    finally:
        await mgr.disconnect()
        srv.close()
        await srv.wait_closed()


async def _noop(*args, **kwargs):
    return None


def test_pending_reconnect_leaves_healthy_connection_alone():
    connections, connected = asyncio.run(_run_scenario())
    assert connected
    assert connections == 1
