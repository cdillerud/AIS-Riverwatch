"""
MongoDB indexes, created at startup (idempotent).

Before 2026-11-10 the only index was _id: every lockage lookup, login and
session check scanned its collection, and the USACE worker's per-lockage
upsert scanned all of lockage_history each time. Nothing enforced one account
per email or one sighting per vessel (a duplicate sighting already existed).

Unique indexes are preceded by a de-duplication pass that keeps the newest
document, so they can be created on an existing database.
"""
import logging
from typing import Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

ASC, DESC = 1, -1



def _unique_str(field: str) -> dict:
    """Unique among documents that have the field (equality queries imply
    $exists, so the planner can use it); legacy documents without it don't collide."""
    return {"unique": True, "partialFilterExpression": {field: {"$exists": True}}}


# (collection, keys, options)
INDEXES = [
    # Lockage history: per-lock recent lists and averages, per-vessel history,
    # transit learning, calibration windows, and the USACE upsert key.
    ("lockage_history", [("lock_id", ASC), ("recorded_at", DESC)], {}),
    ("lockage_history", [("mmsi", ASC), ("recorded_at", DESC)], {}),
    ("lockage_history", [("source", ASC), ("exit_time", DESC)], {}),
    ("lockage_history", [("source", ASC), ("arrival_time", ASC)], {}),
    # Lock board averages (7 days) and last lockage per lock (60 days) filter on
    # recorded_at alone: both were full collection scans on every board request.
    ("lockage_history", [("recorded_at", DESC)], {}),
    ("lockage_history", [("lock_id", ASC), ("source", ASC), ("usace_vessel_no", ASC),
                         ("vessel_name", ASC), ("entry_time", ASC)], {"name": "usace_upsert_key"}),
    # Accounts and sessions
    ("users", [("email", ASC)], _unique_str("email")),
    ("users", [("user_id", ASC)], _unique_str("user_id")),
    ("users", [("vessels.mmsi", ASC)], {}),   # owner / home-berth lookups by boat
    ("user_sessions", [("session_token", ASC)], _unique_str("session_token")),
    # Expired sessions are deleted by MongoDB itself
    ("user_sessions", [("expires_at", ASC)], {"expireAfterSeconds": 0}),
    # Vessels
    ("vessel_sightings", [("mmsi", ASC)], {"unique": True}),
    ("vessel_history", [("mmsi", ASC), ("recorded_at", DESC)], {}),
    # Bounded growth: per-vessel history beyond 90 days is not used anywhere
    ("vessel_history", [("recorded_at", ASC)], {"expireAfterSeconds": 90 * 24 * 3600}),
    ("vessel_names", [("mmsi", ASC)], {}),
    ("user_settings", [("mmsi", ASC)], {}),
    # Small operational collections
    ("usace_queue", [("lock_no", ASC)], {"unique": True}),
    ("wait_calibration", [("ran_at", DESC)], {}),
    # Arrival predictions logged for scoring (services/arrival_learning.py)
    ("arrival_predictions", [("made_at", ASC)], {"expireAfterSeconds": 45 * 24 * 3600}),
    ("arrival_predictions", [("lock_id", ASC), ("made_at", ASC)], {}),
    # One daily Traffic Report email per subscriber per day.
    ("report_sends", [("date", ASC), ("user_id", ASC)], {"unique": True}),
    ("report_sends", [("sent_at", ASC)], {"expireAfterSeconds": 120 * 24 * 3600}),
    ("arrival_calibration", [("ran_at", DESC)], {}),
    ("lock_status", [("lock_id", ASC)], {}),
    # AIS feed up/down, one sample a minute (feed health / uptime).
    ("feed_samples", [("t", ASC)], {"expireAfterSeconds": 35 * 24 * 3600}),
    # Live wait predictions, scored for the public accuracy page.
    ("wait_predictions", [("lock_id", ASC), ("key", ASC), ("arrived_at", ASC)], {"unique": True}),
    ("wait_predictions", [("arrived_at", ASC)], {"expireAfterSeconds": 180 * 24 * 3600}),
    ("marinas", [("river_mile", ASC)], {}),
    # "Share my trip" links: looked up by token; MongoDB deletes them once expired.
    ("trip_shares", [("token", ASC)], {"unique": True}),
    ("trip_shares", [("expires_at", ASC)], {"expireAfterSeconds": 0}),
    ("trip_shares", [("user_id", ASC), ("created_at", DESC)], {}),
]

# For unique indexes: which field decides the "newest" document to keep.
NEWEST_BY = {
    "users": "last_login",
    "user_sessions": "created_at",
    "vessel_sightings": "timestamp",
    "usace_queue": "fetched_at",
}


async def _dedupe(coll, field: str, newest_by: Optional[str]) -> int:
    removed = 0
    async for group in coll.aggregate([
        {"$group": {"_id": f"${field}", "ids": {"$push": {"id": "$_id", "t": f"${newest_by or '_id'}"}}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}, "_id": {"$ne": None}}},
    ]):
        docs = sorted(group["ids"], key=lambda d: (d.get("t") is not None, d.get("t") or 0), reverse=True)
        stale = [d["id"] for d in docs[1:]]
        if stale:
            res = await coll.delete_many({"_id": {"$in": stale}})
            removed += res.deleted_count
    return removed


async def ensure_indexes(db, indexes: Iterable[Tuple[str, list, dict]] = INDEXES) -> dict:
    """Create all indexes; returns {"created": n, "deduplicated": n, "errors": [...]}."""
    created, removed, errors = 0, 0, []
    for coll_name, keys, opts in indexes:
        coll = db[coll_name]
        try:
            if opts.get("unique") and len(keys) == 1:
                removed += await _dedupe(coll, keys[0][0], NEWEST_BY.get(coll_name))
            await coll.create_index(keys, **opts)
            created += 1
        except Exception as e:  # one bad index must not stop startup
            errors.append(f"{coll_name} {keys}: {e}")
            logger.warning(f"Index {coll_name} {keys} not created: {e}")
    if removed:
        logger.info(f"Removed {removed} duplicate documents before creating unique indexes")
    logger.info(f"Database indexes ensured: {created} ok, {len(errors)} failed")
    return {"created": created, "deduplicated": removed, "errors": errors}
