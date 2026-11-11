"""
Daily Traffic Report: one river day of lock traffic, from the USACE lockage
records (db.lockage_history, source="usace_lpms").

A "day" is a Central-time calendar day (the river's local time); a lockage
counts on the day it finished (exit_time). The report compares each lock with
its own average over the previous 7 days.

`build_report` is pure (rows in, dict out) so it is easy to test; the server
fetches the rows. Renderers turn the dict into:
  - HTML: self-contained, inline styles, table layout, light background, so
    the same file works as an email body, a download, and a printout (PDF).
  - CSV: one row per lock.
  - EML: a ready-to-send email (HTML body + CSV attached) that opens as a
    draft in Outlook / Apple Mail, so it can be emailed with no mail server.
"""
from __future__ import annotations

import csv
import html
import io
import statistics as st
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate
from typing import Dict, Iterable, List, Optional, Tuple

LONGEST_WAITS_SHOWN = 5
# A day counts as notably busier/quieter than usual beyond this many percent.
NOTABLE_CHANGE_PCT = 25


# --------------------------------------------------------------------------
# Central time without tz data (Windows hosts often lack the tzdata package).
# US rule since 2007: CDT from the 2nd Sunday of March 02:00 local to the 1st
# Sunday of November 02:00 local.
# --------------------------------------------------------------------------
def _nth_sunday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def central_offset(at_utc: datetime) -> timedelta:
    """UTC offset of US Central time at a UTC instant (-5 h CDT, -6 h CST)."""
    if at_utc.tzinfo is None:
        at_utc = at_utc.replace(tzinfo=timezone.utc)
    y = at_utc.year
    dst_start = datetime.combine(_nth_sunday(y, 3, 2), datetime.min.time(), timezone.utc) + timedelta(hours=8)
    dst_end = datetime.combine(_nth_sunday(y, 11, 1), datetime.min.time(), timezone.utc) + timedelta(hours=7)
    return timedelta(hours=-5) if dst_start <= at_utc < dst_end else timedelta(hours=-6)


def to_central(at_utc: datetime) -> datetime:
    if at_utc.tzinfo is None:
        at_utc = at_utc.replace(tzinfo=timezone.utc)
    off = central_offset(at_utc)
    return at_utc.astimezone(timezone(off, "CDT" if off == timedelta(hours=-5) else "CST"))


def central_today(now_utc: Optional[datetime] = None) -> date:
    return to_central(now_utc or datetime.now(timezone.utc)).date()


def day_bounds_utc(day: date) -> Tuple[datetime, datetime]:
    """[start, end) of a Central calendar day, as aware UTC datetimes."""
    def local_midnight(d: date) -> datetime:
        guess = datetime.combine(d, datetime.min.time(), timezone.utc) + timedelta(hours=6)
        return datetime.combine(d, datetime.min.time(), timezone.utc) - central_offset(guess)
    return local_midnight(day), local_midnight(day + timedelta(days=1))


# --------------------------------------------------------------------------
# Building the report
# --------------------------------------------------------------------------
def _aware(ts) -> Optional[datetime]:
    if not isinstance(ts, datetime):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _kind(r: dict) -> str:
    if r.get("is_tow"):
        return "tow"
    if r.get("is_recreational"):
        return "recreational"
    return "other"


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def _round(v: Optional[float], nd: int = 0):
    if v is None:
        return None
    return round(v, nd) if nd else int(round(v))


def long_single_thresholds(history: Iterable[dict], quantile: float = 0.9,
                           min_samples: int = 20) -> Dict[str, float]:
    """Per lock: how long a one-cut tow lockage takes before it is unusually
    long (the `quantile` of that lock's own one-cut tow lockages). The USACE
    feed doesn't say "knockout"; a single far slower than the lock's usual
    single is the visible sign of one (or of a set-over / slow approach).
    Locks with too few singles get no threshold."""
    by_lock: Dict[str, List[float]] = {}
    for r in history:
        d = _num(r.get("lockage_duration_minutes"))
        if r.get("is_tow") and r.get("cuts") == 1 and d is not None and not r.get("in_progress"):
            by_lock.setdefault(r.get("lock_id"), []).append(d)
    out = {}
    for lid, ds in by_lock.items():
        if len(ds) >= min_samples:
            ds.sort()
            out[lid] = ds[min(len(ds) - 1, int(quantile * len(ds)))]
    return out


def lockage_type(r: dict, long_single_min: Optional[float] = None) -> str:
    """Single / Long single / Double / Triple / Light boat, from the cuts."""
    if not r.get("is_tow"):
        return "Light boat"
    cuts = int(r.get("cuts") or 1)
    if cuts >= 3:
        return "Triple" if cuts == 3 else f"{cuts} cuts"
    if cuts == 2:
        # All the barges in one cut and the towboat alone in the other.
        per_cut = [c.get("barges") for c in (r.get("cut_times") or [])]
        if len(per_cut) == 2 and None not in per_cut and sorted(per_cut)[0] == 0:
            return "Boat separate"
        return "Double"
    d = _num(r.get("lockage_duration_minutes"))
    if long_single_min is not None and d is not None and d > long_single_min:
        return "Long single"
    return "Single"


def _vessel_detail(r: dict, day: date, long_single_min: Optional[float]) -> dict:
    arr = _aware(r.get("arrival_time"))
    ent = _aware(r.get("entry_time"))
    cuts, cut_barges = [], []
    for c in r.get("cut_times") or []:
        s, e = _aware(c.get("start")), _aware(c.get("end"))
        if s and e:
            cuts.append(_round((e - s).total_seconds() / 60))
            cut_barges.append(c.get("barges"))
    return {
        "vessel": (r.get("vessel_name") or "Unknown").strip(),
        "mmsi": r.get("mmsi"),
        "direction": r.get("direction"),
        "barges": int(_num(r.get("barge_count")) or 0),
        "arrived": _arrived(arr, day),
        "started": _arrived(ent, day),
        "wait_min": _round(_num(r.get("wait_time_minutes"))),
        "lockage_min": _round(_num(r.get("lockage_duration_minutes"))),
        "cuts": int(r.get("cuts") or 1),
        "cut_minutes": cuts if len(cuts) > 1 else [],
        "cut_barges": cut_barges if len(cuts) > 1 and None not in cut_barges else [],
        "type": lockage_type(r, long_single_min),
        "_sort": ent or arr or datetime.min.replace(tzinfo=timezone.utc),
    }


def build_report(day: date, rows: Iterable[dict], prior_rows: Iterable[dict],
                 locks: Dict[str, dict], statuses: Optional[Dict[str, dict]] = None,
                 prior_days: int = 7, now: Optional[datetime] = None,
                 long_single_min: Optional[Dict[str, float]] = None) -> dict:
    """rows: the day's completed lockages; prior_rows: the `prior_days` days
    before it (for the usual-traffic comparison); locks: config.LOCKS;
    statuses: lock_id -> {status, closure_info} as of now (optional);
    long_single_min: per-lock long-single thresholds (long_single_thresholds)."""
    long_single_min = long_single_min or {}
    now = now or datetime.now(timezone.utc)
    statuses = statuses or {}
    start, end = day_bounds_utc(day)
    rows = [r for r in rows if not r.get("in_progress")]
    by_lock: Dict[str, List[dict]] = {lid: [] for lid in locks}
    for r in rows:
        if r.get("lock_id") in by_lock:
            by_lock[r["lock_id"]].append(r)
    prior_count: Dict[str, int] = {lid: 0 for lid in locks}
    for r in prior_rows:
        if r.get("lock_id") in prior_count and not r.get("in_progress"):
            prior_count[r["lock_id"]] += 1

    lock_rows = []
    for lid, info in sorted(locks.items(), key=lambda kv: -kv[1].get("river_mile", 0)):
        rs = by_lock[lid]
        kinds = [_kind(r) for r in rs]
        tow_waits = [w for r in rs if _kind(r) == "tow" for w in [_num(r.get("wait_time_minutes"))] if w is not None]
        rec_waits = [w for r in rs if _kind(r) == "recreational" for w in [_num(r.get("wait_time_minutes"))] if w is not None]
        all_waits = [w for r in rs for w in [_num(r.get("wait_time_minutes"))] if w is not None]
        durations = [d for r in rs for d in [_num(r.get("lockage_duration_minutes"))] if d is not None]
        usual = prior_count[lid] / prior_days if prior_days else None
        status = statuses.get(lid) or {}
        vessels = sorted((_vessel_detail(r, day, long_single_min.get(lid)) for r in rs
                          if _kind(r) != "recreational"), key=lambda v: v["_sort"])
        for v in vessels:
            v.pop("_sort")
        types = [v["type"] for v in vessels]
        lock_rows.append({
            "vessels": vessels,
            "singles": types.count("Single") + types.count("Long single"),
            "long_singles": types.count("Long single"),
            "doubles": types.count("Double"),
            "boat_separate": types.count("Boat separate"),
            "triples": sum(1 for t in types if t == "Triple" or t.endswith("cuts")),
            "light_boats": types.count("Light boat"),
            "long_single_over_min": _round(long_single_min.get(lid)),
            "lock_id": lid,
            "name": info.get("name", lid),
            "river_mile": info.get("river_mile"),
            "lockages": len(rs),
            "upbound": sum(1 for r in rs if r.get("direction") == "upbound"),
            "downbound": sum(1 for r in rs if r.get("direction") == "downbound"),
            "tows": kinds.count("tow"),
            "recreational": kinds.count("recreational"),
            "other": kinds.count("other"),
            "barges": int(sum(_num(r.get("barge_count")) or 0 for r in rs if _kind(r) == "tow")),
            "median_tow_wait_min": _round(st.median(tow_waits)) if tow_waits else None,
            "median_rec_wait_min": _round(st.median(rec_waits)) if rec_waits else None,
            "max_wait_min": _round(max(all_waits)) if all_waits else None,
            "avg_lockage_min": _round(st.mean(durations)) if durations else None,
            "usual_lockages": _round(usual, 1),
            "has_data": bool(rs) or prior_count[lid] > 0,
            "status": status.get("status") or "UNKNOWN",
            "closure_info": status.get("closure_info"),
        })

    waits = []
    for r in rows:
        w = _num(r.get("wait_time_minutes"))
        if w is None or r.get("lock_id") not in locks:
            continue
        arr = _aware(r.get("arrival_time"))
        waits.append({
            "vessel": (r.get("vessel_name") or "Unknown").strip(),
            "lock_id": r["lock_id"],
            "lock_name": locks[r["lock_id"]].get("name", r["lock_id"]),
            "wait_min": _round(w),
            "kind": _kind(r),
            "barges": int(_num(r.get("barge_count")) or 0),
            "direction": r.get("direction"),
            "arrived": _arrived(arr, day),
        })
    waits.sort(key=lambda w: -w["wait_min"])

    tows = [r for r in rows if _kind(r) == "tow" and r.get("lock_id") in locks]
    tow_waits = [w for r in tows for w in [_num(r.get("wait_time_minutes"))] if w is not None]
    rec_waits = [w for r in rows if _kind(r) == "recreational" and r.get("lock_id") in locks
                 for w in [_num(r.get("wait_time_minutes"))] if w is not None]
    counted = lock_rows
    total =sum(lr["lockages"] for lr in counted)
    usual_total = sum(prior_count.values()) / prior_days if prior_days else None
    totals = {
        "lockages": total,
        "tows": sum(lr["tows"] for lr in counted),
        "recreational": sum(lr["recreational"] for lr in counted),
        "other": sum(lr["other"] for lr in counted),
        "barges": sum(lr["barges"] for lr in counted),
        "singles": sum(lr["singles"] for lr in counted),
        "long_singles": sum(lr["long_singles"] for lr in counted),
        "doubles": sum(lr["doubles"] for lr in counted),
        "boat_separate": sum(lr["boat_separate"] for lr in counted),
        "triples": sum(lr["triples"] for lr in counted),
        "light_boats": sum(lr["light_boats"] for lr in counted),
        "upbound": sum(lr["upbound"] for lr in counted),
        "downbound": sum(lr["downbound"] for lr in counted),
        "median_tow_wait_min": _round(st.median(tow_waits)) if tow_waits else None,
        "median_rec_wait_min": _round(st.median(rec_waits)) if rec_waits else None,
        "tow_hours_waiting": _round(sum(tow_waits) / 60, 1) if tow_waits else 0,
        "usual_lockages": _round(usual_total, 1),
        "vs_usual_pct": _round((total - usual_total) / usual_total * 100) if usual_total else None,
    }

    complete = now >= end
    return {
        "date": day.isoformat(),
        "title": f"River Traffic Report — {day.strftime('%A, %B')} {day.day}, {day.year}",
        "window": {"start": start.isoformat(), "end": end.isoformat(), "timezone": "US Central"},
        "generated_at": now.isoformat(),
        "complete": complete,
        "totals": totals,
        "locks": lock_rows,
        "longest_waits": waits[:LONGEST_WAITS_SHOWN],
        "closures": [{"lock_id": lr["lock_id"], "name": lr["name"], "status": lr["status"],
                      "info": lr["closure_info"]}
                     for lr in lock_rows if lr["status"] in ("CLOSED", "RESTRICTED")],
        "no_data_locks": [lr["name"] for lr in lock_rows if not lr["has_data"]],
        "highlights": _highlights(lock_rows, totals, waits, complete),
        "source": "USACE Lock Performance Monitoring System (lock operator records)",
    }


def _clock(t: datetime) -> str:
    """'9:05 PM' on any platform (strftime's %-I is not portable)."""
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _arrived(arr: Optional[datetime], day: date) -> Optional[str]:
    """Arrival time; with the date when the boat arrived on an earlier day."""
    if not arr:
        return None
    local = to_central(arr)
    if local.date() == day:
        return _clock(local)
    return f"{local.strftime('%b')} {local.day}, {_clock(local)}"


def _fmt_minutes(m: Optional[float]) -> str:
    if m is None:
        return "—"
    m = int(round(m))
    if m < 60:
        return f"{m} min"
    h, mm = divmod(m, 60)
    return f"{h} h {mm:02d} min" if mm else f"{h} h"


def _highlights(lock_rows: List[dict], totals: dict, waits: List[dict], complete: bool) -> List[str]:
    out: List[str] = []
    if not complete:
        out.append("Day still in progress: counts so far.")
    if totals["lockages"] == 0:
        out.append("No completed lockages were reported for this day.")
        return out
    vs = totals.get("vs_usual_pct")
    if vs is not None and complete:
        if vs >= NOTABLE_CHANGE_PCT:
            out.append(f"Busier than usual: {totals['lockages']} lockages vs about {totals['usual_lockages']:g} a day this past week (+{vs}%).")
        elif vs <= -NOTABLE_CHANGE_PCT:
            out.append(f"Quieter than usual: {totals['lockages']} lockages vs about {totals['usual_lockages']:g} a day this past week ({vs}%).")
        else:
            out.append(f"A typical day: {totals['lockages']} lockages (about {totals['usual_lockages']:g} a day this past week).")
    busiest = max(lock_rows, key=lambda lr: lr["lockages"])
    out.append(f"Busiest lock: {busiest['name']} with {busiest['lockages']} lockages.")
    slow = [lr for lr in lock_rows if lr["median_tow_wait_min"] is not None and lr["tows"] >= 2]
    if slow:
        worst = max(slow, key=lambda lr: lr["median_tow_wait_min"])
        if worst["median_tow_wait_min"] >= 30:
            out.append(f"Slowest for tows: {worst['name']}, typical wait {_fmt_minutes(worst['median_tow_wait_min'])}.")
    if waits and waits[0]["wait_min"] >= 60:
        w = waits[0]
        out.append(f"Longest wait: {w['vessel']} at {w['lock_name']}, {_fmt_minutes(w['wait_min'])}.")
    n_rec = totals["recreational"]
    if n_rec:
        rec_wait = totals["median_rec_wait_min"]
        plural = "s" if n_rec != 1 else ""
        if rec_wait is None:
            tail = "."
        elif rec_wait == 0:
            tail = ", most with no wait." if n_rec > 1 else ", no wait."
        else:
            tail = f", typical wait {_fmt_minutes(rec_wait)}."
        out.append(f"{n_rec} pleasure-boat lockage{plural}{tail}")
    return out


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
_C = {"ink": "#0f172a", "muted": "#64748b", "line": "#e2e8f0", "head": "#f1f5f9",
      "accent": "#0e7490", "bad": "#b91c1c", "warn": "#b45309", "bg": "#ffffff"}


def _e(v) -> str:
    return html.escape("" if v is None else str(v))


def _cell(v, align="right", color=None, bold=False) -> str:
    style = f"padding:6px 8px;border-bottom:1px solid {_C['line']};text-align:{align};white-space:nowrap;"
    if color:
        style += f"color:{color};"
    if bold:
        style += "font-weight:600;"
    return f'<td style="{style}">{v}</td>'


def render_html(report: dict, app_url: Optional[str] = None) -> str:
    t = report["totals"]
    dash = "—"
    dash_sep = " — "
    in_progress = "" if report["complete"] else " — day in progress"

    def n(v):
        return dash if v is None else _e(v)

    stat = lambda label, value, sub="": (
        f'<td style="padding:10px 12px;border:1px solid {_C["line"]};vertical-align:top;width:25%;">'
        f'<div style="font-size:11px;color:{_C["muted"]};text-transform:uppercase;letter-spacing:.04em;">{label}</div>'
        f'<div style="font-size:22px;font-weight:700;color:{_C["ink"]};margin-top:2px;">{value}</div>'
        f'<div style="font-size:12px;color:{_C["muted"]};">{sub}</div></td>')
    vs = t.get("vs_usual_pct")
    vs_txt = "" if vs is None or not report["complete"] else (f"{'+' if vs > 0 else ''}{vs}% vs past week")
    stats = (stat("Lockages", t["lockages"], vs_txt)
             + stat("Tows", t["tows"], f"{t['barges']:,} barges")
             + stat("Pleasure boats", t["recreational"], f"{t['other']} other vessels" if t["other"] else "")
             + stat("Typical tow wait", _e(_fmt_minutes(t["median_tow_wait_min"])),
                    f"{t['tow_hours_waiting']:g} tow-hours waiting" if t["tow_hours_waiting"] else ""))

    hl = "".join(f'<li style="margin:3px 0;">{_e(h)}</li>' for h in report["highlights"])

    head = "".join(
        f'<th style="padding:6px 8px;background:{_C["head"]};border-bottom:1px solid {_C["line"]};'
        f'text-align:{a};font-size:11px;color:{_C["muted"]};text-transform:uppercase;white-space:nowrap;">{h}</th>'
        for h, a in [("Lock", "left"), ("RM", "right"), ("Lockages", "right"), ("Usual", "right"),
                     ("Up / Down", "right"), ("Tows", "right"), ("Barges", "right"), ("Pleasure", "right"),
                     ("Tow wait", "right"), ("Longest", "right")])
    body = []
    for lr in report["locks"]:
        if not lr["has_data"]:
            continue
        tw = lr["median_tow_wait_min"]
        tw_color = _C["bad"] if tw is not None and tw >= 120 else _C["warn"] if tw is not None and tw >= 45 else None
        usual = lr["usual_lockages"]
        busy = usual and lr["lockages"] >= usual * (1 + NOTABLE_CHANGE_PCT / 100) and lr["lockages"] - usual >= 3
        name = _e(lr["name"].replace("Lock & Dam ", "L&D "))
        if lr["status"] in ("CLOSED", "RESTRICTED"):
            name += f' <span style="color:{_C["bad"]};font-size:11px;">{_e(lr["status"].title())}</span>'
        body.append(
            "<tr>" + _cell(name, "left")
            + _cell(n(lr["river_mile"])) + _cell(lr["lockages"], bold=True, color=_C["warn"] if busy else None)
            + _cell(dash if usual is None else f"{usual:g}", color=_C["muted"])
            + _cell(f"{lr['upbound']} / {lr['downbound']}") + _cell(lr["tows"]) + _cell(f"{lr['barges']:,}")
            + _cell(lr["recreational"]) + _cell(_e(_fmt_minutes(tw)), color=tw_color)
            + _cell(_e(_fmt_minutes(lr["max_wait_min"]))) + "</tr>")
    table = (f'<table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;font-size:13px;">'
             f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>")

    waits_html = ""
    if report["longest_waits"]:
        rows = "".join(
            "<tr>" + _cell(_e(w["vessel"]), "left", bold=True) + _cell(_e(w["lock_name"]), "left")
            + _cell(_e(_fmt_minutes(w["wait_min"]))) + _cell(_e(w["arrived"] or dash))
            + _cell(_e({"tow": f"Tow, {w['barges']} barges" if w["barges"] else "Tow",
                        "recreational": "Pleasure boat"}.get(w["kind"], "Other")), "left")
            + _cell(_e((w["direction"] or "").title() or dash), "left") + "</tr>"
            for w in report["longest_waits"])
        wh = "".join(
            f'<th style="padding:6px 8px;background:{_C["head"]};text-align:{a};font-size:11px;color:{_C["muted"]};'
            f'text-transform:uppercase;border-bottom:1px solid {_C["line"]};">{h}</th>'
            for h, a in [("Vessel", "left"), ("Lock", "left"), ("Wait", "right"), ("Arrived", "right"),
                         ("Type", "left"), ("Direction", "left")])
        waits_html = (f'<h2 style="font-size:15px;margin:24px 0 8px;color:{_C["ink"]};">Longest waits</h2>'
                      f'<table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;font-size:13px;">'
                      f"<thead><tr>{wh}</tr></thead><tbody>{rows}</tbody></table>")

    detail_html = _render_vessel_detail(report)

    closures = ""
    if report["closures"]:
        items = "".join(f'<li><b>{_e(c["name"])}</b>: {_e(c["status"].title())}'
                        f'{(dash_sep + _e(c["info"])) if c.get("info") else ""}</li>' for c in report["closures"])
        closures = (f'<h2 style="font-size:15px;margin:24px 0 8px;color:{_C["bad"]};">Closures and restrictions (now)</h2>'
                    f'<ul style="margin:0;padding-left:18px;font-size:13px;">{items}</ul>')

    gen = to_central(datetime.fromisoformat(report["generated_at"]))
    footer_bits = [f"Source: {_e(report['source'])}.",
                   "Counts are completed lockages that finished during the day (US Central time); "
                   "a tow locked through in cuts counts once. Usual = average a day over the previous 7 days "
                   "(orange when well above it). Tow wait = the typical (median) wait from arrival to start of "
                   "lockage; Longest = longest wait of any vessel.",
                   "Lockage type comes from the cuts USACE logged: Single = one lockage; Double = the barges "
                   "split across two lockages (e.g. 9+6); Boat separate = all barges in one lockage and the "
                   "towboat alone in a second; Long single = one lockage, but slower than 9 in 10 singles at "
                   "that lock over the past 30 days, which usually means the towboat had to be reconfigured "
                   "(e.g. a knockout, moved alongside the barges to fit). USACE's public feed doesn't name "
                   "the lockage type, so these are read from its timings and barge counts.",
                   f"Generated {gen.strftime('%b')} {gen.day}, {gen.year} {_clock(gen)} {gen.tzname()}."]
    if report["no_data_locks"]:
        footer_bits.append("No USACE data: " + _e(", ".join(report["no_data_locks"])) + ".")
    if app_url:
        footer_bits.append(f'Live lock timing: <a href="{_e(app_url)}" style="color:{_C["accent"]};">{_e(app_url)}</a>')
    footer = "".join(f'<p style="margin:4px 0;">{b}</p>' for b in footer_bits)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(report['title'])}</title>
<style>@media print {{ body {{ margin: 0; }} .wrap {{ max-width: none !important; }} }}</style>
</head>
<body style="margin:0;padding:0;background:{_C['bg']};color:{_C['ink']};font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
<div class="wrap" style="max-width:920px;margin:0 auto;padding:20px 16px;">
<div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:{_C['accent']};">RIVERWATCH</div>
<h1 style="font-size:22px;margin:4px 0 2px;">{_e(report['title'])}</h1>
<div style="font-size:13px;color:{_C['muted']};">Upper Mississippi, Minneapolis to St. Louis{in_progress}</div>
<table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;margin:16px 0;"><tr>{stats}</tr></table>
<ul style="margin:0 0 16px;padding-left:18px;font-size:14px;line-height:1.45;">{hl}</ul>
{closures}
<h2 style="font-size:15px;margin:24px 0 8px;color:{_C['ink']};">By lock, upstream to downstream</h2>
<div style="overflow-x:auto;">{table}</div>
{waits_html}
{detail_html}
<div style="margin-top:24px;padding-top:10px;border-top:1px solid {_C['line']};font-size:11px;color:{_C['muted']};line-height:1.4;">{footer}</div>
</div></body></html>"""


_TYPE_COLOR = {"Long single": _C["warn"], "Double": _C["accent"], "Boat separate": _C["accent"],
               "Triple": _C["bad"]}


def _type_label(v: dict) -> str:
    """'Double (9+6 barges, 52 + 61 min)'."""
    label = v["type"]
    bits = []
    if v.get("cut_barges") and v["type"] != "Boat separate":
        bits.append("+".join(str(b) for b in v["cut_barges"]) + " barges")
    if v["cut_minutes"]:
        bits.append(" + ".join(str(m) for m in v["cut_minutes"]) + " min")
    return label + (f" ({', '.join(bits)})" if bits else "")


def _render_vessel_detail(report: dict) -> str:
    """Every tow and light boat at each lock, in the order they locked."""
    dash = "—"
    th = lambda h, a: (f'<th style="padding:5px 8px;background:{_C["head"]};text-align:{a};font-size:11px;'
                       f'color:{_C["muted"]};text-transform:uppercase;border-bottom:1px solid {_C["line"]};'
                       f'white-space:nowrap;">{h}</th>')
    head = "".join(th(h, a) for h, a in [("Vessel", "left"), ("Dir", "left"), ("Barges", "right"),
                                         ("Arrived", "right"), ("Wait", "right"), ("Started", "right"),
                                         ("Lockage", "right"), ("Type", "left")])
    blocks = []
    for lr in report["locks"]:
        vs = lr.get("vessels") or []
        if not vs:
            continue
        counts = [f"{lr['tows']} tow{'s' if lr['tows'] != 1 else ''}"]
        for n, word in ((lr["singles"], "single"), (lr["doubles"], "double"), (lr["triples"], "triple"),
                        (lr["light_boats"], "light boat")):
            if n:
                counts.append(f"{n} {word}{'s' if n != 1 else ''}")
        if lr["boat_separate"]:
            counts.append(f"{lr['boat_separate']} boat separate")
        if lr["long_singles"]:
            counts.append(f"{lr['long_singles']} long")
        rows = "".join(
            "<tr>" + _cell(_e(v["vessel"]), "left", bold=True)
            + _cell({"upbound": "Up", "downbound": "Down"}.get(v["direction"], dash), "left")
            + _cell(v["barges"] if v["type"] != "Light boat" else dash)
            + _cell(_e(v["arrived"] or dash)) + _cell(_e(_fmt_minutes(v["wait_min"])))
            + _cell(_e(v["started"] or dash)) + _cell(_e(_fmt_minutes(v["lockage_min"])))
            + _cell(_e(_type_label(v)), "left", color=_TYPE_COLOR.get(v["type"])) + "</tr>"
            for v in vs)
        blocks.append(
            f'<h3 style="font-size:13px;margin:16px 0 4px;color:{_C["ink"]};">{_e(lr["name"])} '
            f'<span style="font-weight:400;color:{_C["muted"]};">RM {_e(lr["river_mile"])} · '
            f'{_e(", ".join(counts))}</span></h3>'
            f'<div style="overflow-x:auto;"><table role="presentation" cellspacing="0" cellpadding="0" '
            f'style="border-collapse:collapse;width:100%;font-size:12px;"><thead><tr>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")
    if not blocks:
        return ""
    return (f'<h2 style="font-size:15px;margin:28px 0 4px;color:{_C["ink"]};">Tows by lock</h2>'
            f'<div style="font-size:12px;color:{_C["muted"]};">Every tow and light boat, in the order they '
            f"locked through. Pleasure boats are counted above.</div>" + "".join(blocks))


TOW_CSV_COLUMNS = ["date", "lock_id", "lock_name", "river_mile", "vessel", "mmsi", "direction", "barges",
                   "arrived", "started", "wait_min", "lockage_min", "type", "cuts", "cut_barges",
                   "cut_minutes"]


def render_tows_csv(report: dict) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TOW_CSV_COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    w.writeheader()
    for lr in report["locks"]:
        for v in lr.get("vessels") or []:
            w.writerow({**v, "date": report["date"], "lock_id": lr["lock_id"], "lock_name": lr["name"],
                        "river_mile": lr["river_mile"],
                        "cut_barges": "+".join(str(b) for b in v["cut_barges"]),
                        "cut_minutes": " + ".join(str(m) for m in v["cut_minutes"])})
    return buf.getvalue()


CSV_COLUMNS = ["date", "lock_id", "name", "river_mile", "lockages", "upbound", "downbound", "tows",
               "barges", "recreational", "other", "median_tow_wait_min", "median_rec_wait_min",
               "max_wait_min", "avg_lockage_min", "usual_lockages", "singles", "long_singles", "doubles",
               "boat_separate", "triples", "light_boats", "status"]


def render_csv(report: dict) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    w.writeheader()
    for lr in report["locks"]:
        if lr["has_data"]:
            w.writerow({**lr, "date": report["date"]})
    return buf.getvalue()


def plain_text(report: dict) -> str:
    t = report["totals"]
    lines = [report["title"], "",
             f"Lockages: {t['lockages']}  |  Tows: {t['tows']} ({t['barges']} barges)  |  "
             f"Pleasure boats: {t['recreational']}  |  Typical tow wait: {_fmt_minutes(t['median_tow_wait_min'])}", ""]
    lines += [f"- {h}" for h in report["highlights"]]
    lines += ["", "By lock:"]
    for lr in report["locks"]:
        if lr["lockages"]:
            lines.append(f"  {lr['name']}: {lr['lockages']} lockages, {lr['tows']} tows, "
                         f"typical tow wait {_fmt_minutes(lr['median_tow_wait_min'])}")
    return "\n".join(lines) + "\n"


def filename(report: dict, ext: str) -> str:
    return f"riverwatch-traffic-{report['date']}.{ext}"


def render_eml(report: dict, to: Optional[str] = None, sender: Optional[str] = None,
               app_url: Optional[str] = None) -> bytes:
    """A complete email. Without `to`/`sender` it is an unsent draft
    (X-Unsent: 1), which Outlook opens ready to address and send."""
    msg = build_email(report, to=to, sender=sender, app_url=app_url)
    if not to:
        msg["X-Unsent"] = "1"
    return bytes(msg)


def build_email(report: dict, to: Optional[str] = None, sender: Optional[str] = None,
                app_url: Optional[str] = None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = report["title"]
    if sender:
        msg["From"] = sender
    if to:
        msg["To"] = to
    msg["Date"] = formatdate(localtime=False)
    msg.set_content(plain_text(report))
    msg.add_alternative(render_html(report, app_url=app_url), subtype="html")
    msg.add_attachment(render_csv(report).encode("utf-8"), maintype="text", subtype="csv",
                       filename=filename(report, "csv"))
    msg.add_attachment(render_tows_csv(report).encode("utf-8"), maintype="text", subtype="csv",
                       filename=f"riverwatch-tows-{report['date']}.csv")
    return msg
