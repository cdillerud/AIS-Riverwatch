"""Feed monitor glue in server.py (alert email text, outage start across restarts)."""
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")

NOW = datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)


def test_outage_start_survives_restart(monkeypatch):
    monkeypatch.setattr(server, "_feed_last_ok", NOW - timedelta(hours=6))
    samples = [(NOW - timedelta(minutes=m), False) for m in range(3, -1, -1)]
    assert server._feed_summary(samples, NOW)["down_since"] == (NOW - timedelta(hours=6)).isoformat()
    monkeypatch.setattr(server, "_feed_last_ok", None)
    assert server._feed_summary(samples, NOW)["down_since"] == samples[0][0].isoformat()


def test_alert_messages(monkeypatch):
    monkeypatch.setenv("REPORT_EMAIL_FROM", "River Watch <alerts@example.com>")
    down = server._feed_alert_message("down", NOW - timedelta(minutes=20), NOW, "admin@example.com")
    assert "down since" in down["Subject"] and "Boat Beacon" in down.get_content()
    up = server._feed_alert_message("up", NOW - timedelta(minutes=90), NOW, "admin@example.com")
    assert up["Subject"].endswith("back after 90 min")
