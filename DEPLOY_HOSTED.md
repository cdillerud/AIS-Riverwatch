# Deploying River Watch to a hosted server

A single small VM runs everything: MongoDB, the backend, the built frontend,
Caddy (HTTPS with automatic Let's Encrypt certificates) and a nightly database
backup. About 30 minutes end to end.

## What you need

| Item | Suggestion | Cost |
|---|---|---|
| VM | Hetzner Cloud **CX22** (2 vCPU, 4 GB RAM), Ubuntu 24.04, US region (Ashburn or Hillsboro) | ~€5/month |
| Domain | Any registrar; e.g. `riverwatch.yourdomain.com` | ~$12/year |
| Google sign-in (optional) | OAuth client ID from Google Cloud Console | free |

## 1. Create the server

1. In Hetzner Cloud: **Add Server** → Ubuntu 24.04, CX22, add your SSH key.
2. Note its public IPv4 address.
3. At your DNS provider, add an **A record**: `riverwatch.yourdomain.com` → that IP.
   Wait until `nslookup riverwatch.yourdomain.com` returns it (usually minutes).

## 2. Prepare the server

```bash
ssh root@<server-ip>

# Firewall: SSH + web only (Mongo is never exposed)
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable

# Docker (official install script)
curl -fsSL https://get.docker.com | sh

# The code
git clone https://github.com/cdillerud/AIS-Riverwatch.git /opt/riverwatch
cd /opt/riverwatch
```

## 3. Configure

```bash
cp deploy/production.env.example .env
nano .env    # set RIVERWATCH_DOMAIN, SUPER_ADMIN_EMAIL, ACME_EMAIL, AIS_INGEST_TOKEN
```

`AIS_INGEST_TOKEN`: generate with `openssl rand -hex 24`.

## 4. Start

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker builder prune -f      # build cache fills small disks quickly
docker compose -f docker-compose.prod.yml logs -f caddy backend
```

Caddy obtains the certificate on first start (watch for `certificate obtained successfully`).
Open `https://riverwatch.yourdomain.com`, register with `SUPER_ADMIN_EMAIL`.

Within a few minutes the Locks board fills from USACE (the backend walks the
locks one request every ~13 s - USACE allows 5 per minute) and 30 days of
lockage history are imported.

## 5. Google sign-in (optional)

Google Cloud Console → APIs & Services → Credentials → **Create OAuth client ID** →
Web application → Authorized JavaScript origins: `https://riverwatch.yourdomain.com`.
Put the client ID in `.env` as `GOOGLE_CLIENT_ID`, then
`docker compose -f docker-compose.prod.yml up -d backend`.

## Live AIS from a boat (optional)

A hosted server can't reach a phone on a boat's Wi-Fi. To feed Boat Beacon
traffic in, run the push relay (`ais_push_relay/`) on a computer aboard,
pointed at `https://riverwatch.yourdomain.com/api/ais/ingest` with the same
`AIS_INGEST_TOKEN`. Without it, River Watch still has USACE lock data and
users' phone GPS.

## Operating it

**Update to the latest `main`:**
```bash
cd /opt/riverwatch && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker builder prune -f && df -h /
```

**Backups:** one compressed archive per day in `/opt/riverwatch/backups`, 14 days kept.
Copy them off the server periodically (e.g. `scp root@<ip>:/opt/riverwatch/backups/* .`).

**Restore a backup:**
```bash
docker compose -f docker-compose.prod.yml exec -T mongodb \
  mongorestore --archive --gzip --drop < backups/riverwatch-YYYY-MM-DD.archive.gz
```

**Health checks:** `https://riverwatch.yourdomain.com/api/locks/board` returns
the lock board; `docker compose -f docker-compose.prod.yml ps` shows all five
services `running`.

**Recalibrate wait estimates** as history grows:
```bash
docker compose -f docker-compose.prod.yml exec backend \
  python scripts/backtest_waits.py
```
then update `CALIBRATION` in `backend/services/lock_board.py` if the fit changes.
