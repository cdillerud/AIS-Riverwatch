# Riverwatch Runtime

Current working browser entrypoint:

http://34.172.47.153/login

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
- Backend host port: `8001`
- AIS relay host port: `8088`
- Mongo runs internally in the Docker network.

Production browser access should not depend on port 3000.

Do not use:

- `http://34.172.47.153:3000/login`
- `http://34.172.47.153:8001`
- old container names: `riverwatch-backend`, `riverwatch-frontend`, `riverwatch-mongo`

Correct user-facing URL:

http://34.172.47.153/login

Frontend deployment:

./scripts/deploy-static-frontend.sh

Healthcheck:

./scripts/healthcheck-nginx.sh
