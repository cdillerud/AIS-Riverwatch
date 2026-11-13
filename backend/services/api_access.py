"""
Which API paths answer without signing in.

Every page of the app requires login, but until now ~25 data endpoints
(/api/vessels among them) answered anyone. /api/vessels includes users' own
boats posted from their phones, so anyone could follow a boater's position
without an account. Now everything under /api needs a session except:

  - sign-in itself and the public config the login page needs
  - /api/health (uptime monitors) and /api/locks (static lock reference list,
    used by install health checks)
  - /api/ais/ingest (relays authenticate with X-Ingest-Token instead)
  - /api/install/* (Pi bootstrap downloads, no data)
  - /api/accuracy (published prediction accuracy; aggregates, no user data)

Rollback: API_LOGIN_REQUIRED=false restores the old open behaviour.
"""
import os

PUBLIC_EXACT = frozenset({
    "/api", "/api/",
    "/api/health",
    "/api/locks",
    "/api/accuracy",
    "/api/ais/ingest",
    "/api/install/tarball",
    "/api/install/bootstrap",
})
PUBLIC_PREFIXES = ("/api/auth/",)


def login_required() -> bool:
    return os.environ.get("API_LOGIN_REQUIRED", "true").strip().lower() not in ("0", "false", "no", "off")


def is_public(path: str) -> bool:
    path = path or ""
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)
