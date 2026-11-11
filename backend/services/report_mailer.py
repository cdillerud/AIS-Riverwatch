"""
Sends the daily Traffic Report by email, when the server has an SMTP account.

Off unless REPORT_SMTP_HOST and REPORT_EMAIL_FROM are set (any SMTP provider:
Gmail/Google Workspace app password, Microsoft 365, SendGrid, Mailgun, SES...):

  REPORT_SMTP_HOST      smtp.example.com
  REPORT_SMTP_PORT      587 (STARTTLS) or 465 (SSL)
  REPORT_SMTP_USER      login (optional)
  REPORT_SMTP_PASSWORD  password / app password (optional)
  REPORT_EMAIL_FROM     "RiverWatch <reports@example.com>"
  REPORT_SEND_HOUR      Central-time hour to send yesterday's report (default 6)
  APP_PUBLIC_URL        link printed in the report footer (optional)

Without it, people still download the report (HTML / CSV / ready-to-send .eml).
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional


def configured() -> bool:
    return bool(os.environ.get("REPORT_SMTP_HOST") and os.environ.get("REPORT_EMAIL_FROM"))


def sender() -> Optional[str]:
    return os.environ.get("REPORT_EMAIL_FROM")


def app_url() -> Optional[str]:
    return os.environ.get("APP_PUBLIC_URL") or None


def send_hour() -> int:
    try:
        return max(0, min(23, int(os.environ.get("REPORT_SEND_HOUR", "6"))))
    except ValueError:
        return 6


def send(msg: EmailMessage, timeout: float = 30.0) -> None:
    """Blocking SMTP send; call from a worker thread (asyncio.to_thread)."""
    host = os.environ["REPORT_SMTP_HOST"]
    port = int(os.environ.get("REPORT_SMTP_PORT", "587"))
    user = os.environ.get("REPORT_SMTP_USER")
    password = os.environ.get("REPORT_SMTP_PASSWORD")
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=timeout) as s:
            if user:
                s.login(user, password or "")
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as s:
            s.starttls(context=ctx)
            if user:
                s.login(user, password or "")
            s.send_message(msg)
