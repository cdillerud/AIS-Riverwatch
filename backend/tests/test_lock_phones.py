"""Lock phone numbers ("Call Lock") must match the verified list in config.py everywhere."""
import re
from pathlib import Path

from config import LOCKS

REPO = Path(__file__).resolve().parents[2]


def test_frontend_offline_fallback_matches_backend():
    src = (REPO / "frontend" / "src" / "hooks" / "useLocks.js").read_text(encoding="utf-8")
    fallback = dict(re.findall(r'\{ id: "([a-z0-9_]+)",[^\n]*?phone: "([^"]*)"', src))
    assert fallback, "could not parse FALLBACK_LOCKS"
    for lock_id, phone in fallback.items():
        assert LOCKS[lock_id]["phone"] == phone, (lock_id, phone, LOCKS[lock_id]["phone"])


def test_every_lock_has_its_own_number():
    phones = [info["phone"] for info in LOCKS.values()]
    assert all(re.fullmatch(r"\d{3}-\d{3}-\d{4}", p) for p in phones)
    assert len(set(phones)) == len(phones), "two locks share a phone number"
