"""
Live AIS wins over positions people type in.

A boat's AIS transponder is the ground truth. While an MMSI is being heard on
AIS (the phone/relay feed or aisstream.io), manual, browser-GPS, simulated or
restored positions for it are refused or skipped. Otherwise whoever claimed a
towboat's MMSI first could park it anywhere on everyone's map.

AIS_WINS_MINUTES: Class A reports every 2-10 s underway and every 3 min at
anchor; Class B every 30 s - 3 min. Ten quiet minutes means the boat has left
receiver range, and then the owner's own GPS is the best position we have.
"""
from datetime import datetime, timezone
from typing import Dict, Optional

AIS_WINS_MINUTES = 10

_heard_at: Dict[str, datetime] = {}


def record_position(mmsi: str, at: Optional[datetime] = None) -> None:
    """Call for every AIS position report stored (not for typed-in positions)."""
    if mmsi:
        _heard_at[str(mmsi)] = at or datetime.now(timezone.utc)


def minutes_since_heard(mmsi: str, now: Optional[datetime] = None) -> Optional[float]:
    at = _heard_at.get(str(mmsi).strip()) if mmsi else None
    if at is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - at).total_seconds() / 60)


def on_live_ais(mmsi: str, now: Optional[datetime] = None) -> bool:
    age = minutes_since_heard(mmsi, now)
    return age is not None and age <= AIS_WINS_MINUTES


def refusal(mmsi: str, now: Optional[datetime] = None) -> Optional[str]:
    """Why a typed-in position for `mmsi` is refused, or None if it's allowed."""
    age = minutes_since_heard(mmsi, now)
    if age is None or age > AIS_WINS_MINUTES:
        return None
    ago = "just now" if age < 1 else f"{int(age)} min ago"
    return (f"This boat is on live AIS (last heard {ago}), so its AIS position is used. "
            f"Manual and phone-GPS positions apply after {AIS_WINS_MINUTES} min without AIS.")


def reset() -> None:
    """Tests only."""
    _heard_at.clear()
