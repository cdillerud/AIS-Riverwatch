# River Watch AIS Push Relay
#
# Two-port service running on the LAN-facing host:
#   - HTTP API (default 0.0.0.0:8088): scanner + selection + status
#   - TCP NMEA fanout (default 0.0.0.0:5353): backend connects here to
#     receive the currently-selected Boat Beacon upstream feed.
#
# The relay opens a TCP client connection to the selected upstream
# Boat Beacon IP:port (persisted to /data/state.json), buffers the lines,
# and fans them out byte-for-byte to all connected backend clients on
# port 5353. When the selection changes the upstream is dropped and
# reopened against the new target.
#
# Operators discover their feed by hitting POST /scan/boat-beacon
# (optionally with a subnet override) and then POST /scan/select with
# the chosen ip+port. The relay treats the selected feed as the
# authoritative Boat Beacon source.

FROM python:3.11-slim

WORKDIR /app

# tcpdump is *not* required but useful for ad-hoc debugging on the host.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY *.py /app/
RUN mkdir -p /data
VOLUME ["/data"]

ENV WS_HOST=0.0.0.0 \
    WS_PORT=8088 \
    TCP_HOST=0.0.0.0 \
    TCP_PORT=5353 \
    INGEST_HOST=0.0.0.0 \
    INGEST_PORT=6000 \
    INGEST_IDLE_TIMEOUT=120 \
    STATE_PATH=/data/state.json \
    SCAN_TIMEOUT=0.6 \
    SCAN_READ_BYTES=512 \
    SCAN_READ_TIMEOUT=2.0

EXPOSE 8088 5353 6000

CMD ["python", "-u", "main.py"]
