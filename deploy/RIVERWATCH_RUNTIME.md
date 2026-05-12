# Riverwatch Runtime

Current working browser entrypoint:

http://34.172.47.153/login

The frontend is no longer served by the React dev server in the browser path.

Runtime layout:

- Host nginx listens on ports 80 and 443.
- Static React build is served from `/var/www/riverwatch`.
- `/api/` proxies to backend at `127.0.0.1:8001/api/`.
- `/docs` proxies to backend at `127.0.0.1:8001/docs`.
- `/openapi.json` proxies to backend at `127.0.0.1:8001/openapi.json`.
- `/ws` proxies to backend websocket at `127.0.0.1:8001/ws`.

Docker clean stack:

- Compose project: `riverwatchclean`
- Compose file: `docker-compose.clean.yml`
- Backend port exposed on host: `8001`
- AIS relay port exposed on host: `8088`
- Mongo runs internally in the Docker network.

Do not rely on the frontend dev server on port 3000 for production browser access.

Correct user-facing URL:

http://34.172.47.153/login

Do not use:

- `http://34.172.47.153:3000/login`
- `http://34.172.47.153:8001`
- old `riverwatch-backend`, `riverwatch-frontend`, or `riverwatch-mongo` container names.

Static frontend build process:

1. Build frontend assets with same-origin API:
   - `REACT_APP_BACKEND_URL=`
   - `FAST_REFRESH=false`
   - `CI=false`
   - `GENERATE_SOURCEMAP=false`

2. Copy build output to:
   - `/var/www/riverwatch`

3. Restart nginx:
   - `sudo nginx -t`
   - `sudo systemctl restart nginx`
