"""
Who may see and change which settings.

Two stores:
  db.settings       server-wide defaults and the admin's feed config. Admins
                    write it; everyone reads it, minus the admin's own boat
                    and feed address (PERSONAL_GLOBAL_KEYS).
  db.user_settings  per-boat settings, keyed by MMSI *and* the account that
                    saved them, so one user can't read or overwrite another
                    user's boat by guessing its MMSI. Docs saved before this
                    scoping have no user_id; only admins see those.
"""
from typing import Any, Dict

# Global keys that describe the admin's own boat/feed, not app defaults.
# Before this split, any new user inherited the admin's MMSI as "their" boat.
PERSONAL_GLOBAL_KEYS = frozenset({"user_mmsi", "boat_name", "last_ip", "last_port",
                                  # feed IP/port + MMSI + boat name, saved by /ais/connect
                                  "last_connection_config"})


def is_admin(user: dict) -> bool:
    return bool(user and (user.get("is_admin") or user.get("is_super_admin")))


def visible_global_settings(settings: Dict[str, Any], user: dict) -> Dict[str, Any]:
    if is_admin(user):
        return dict(settings)
    return {k: v for k, v in settings.items() if k not in PERSONAL_GLOBAL_KEYS}


def read_filter(mmsi: str, user: dict) -> dict:
    """Mongo filter for the settings doc this user may read for `mmsi`."""
    if is_admin(user):
        return {"mmsi": mmsi, "$or": [{"user_id": user["user_id"]}, {"user_id": {"$exists": False}}]}
    return {"mmsi": mmsi, "user_id": user["user_id"]}


def write_filter(mmsi: str, user: dict) -> dict:
    """Mongo filter for the doc to upsert. An admin's save adopts a legacy
    (unowned) doc for that MMSI instead of leaving a duplicate behind."""
    return read_filter(mmsi, user)
