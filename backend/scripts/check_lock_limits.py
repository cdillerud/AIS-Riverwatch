"""Re-scrape the USACE district limit tables and compare with
services/lock_limits_data.py.

    cd backend && python scripts/check_lock_limits.py

Prints every difference; exit code 1 if anything changed or a page could not
be read. Update lock_limits_data.py (values and CHECKED) by hand - a changed
table layout should be looked at, not silently trusted.
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import lock_limits as ll  # noqa: E402
from services.lock_limits_data import CHECKED, MVP_URL, MVR_URL  # noqa: E402

UA = {"User-Agent": "RiverWatch/1.0 (Upper Mississippi lock planning)"}


def main() -> int:
    import os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")  # server import needs it; no DB use
    os.environ.setdefault("DB_NAME", "riverwatch")
    import server  # for match_lock_name (whole-number lock-name matching)

    problems = []
    with httpx.Client(headers=UA, follow_redirects=True, timeout=40) as c:
        pages = {}
        for url in (MVP_URL, MVR_URL):
            r = c.get(url)
            if r.status_code != 200:
                problems.append(f"{url}: HTTP {r.status_code}")
            pages[url] = r.text
    mvp = ll.parse_mvp_limits(pages.get(MVP_URL, ""))
    mvr = ll.parse_mvr_limits(pages.get(MVR_URL, ""), server.match_lock_name)
    if len([k for k in mvp if k.startswith("lock_")]) < 11:
        problems.append(f"St. Paul table: only {len(mvp)} rows parsed - layout changed?")
    if len(mvr) < 12:
        problems.append(f"Rock Island table: only {len(mvr)} rows parsed - layout changed?")
    problems += ll.diff_limits(mvp) + ll.diff_limits(mvr)
    updated = ll.mvr_page_updated(pages.get(MVR_URL, ""))
    print(f"Stored limits checked {CHECKED}; Rock Island page updated {updated}")
    for p in problems:
        print(" -", p)
    print("No differences." if not problems else f"{len(problems)} difference(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
