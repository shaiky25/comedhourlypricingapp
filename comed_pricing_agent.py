#!/usr/bin/env python3
"""
Poll ComEd hourly pricing; when the current-hour average is below a threshold
during a configurable local-time window, send email and/or SMS (once per hour).

Typical use: run EV charging, dryer, or other heavy loads when hourly price dips.
Overnight cheap hours: set ALERT_WINDOW_START_HOUR / END to wrap (e.g. 22 and 6).
"""

from __future__ import annotations

import json
import os
import smtplib
import sys
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

API_URL = "https://hourlypricing.comed.com/api?type=currenthouraverage"
STATE_FILE = Path(__file__).resolve().parent / ".comed_notifier_state.json"

# Defaults: 5 AM–11 PM local (override with ALERT_WINDOW_* in .env)
DEFAULT_WINDOW_START_HOUR = 5
DEFAULT_WINDOW_END_HOUR = 23


@dataclass(frozen=True)
class CurrentHourPrice:
    price_cents: float
    millis_utc: int


def load_state() -> dict[str, Any]:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_current_hour_average(session: requests.Session) -> CurrentHourPrice:
    r = session.get(API_URL, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        raise ValueError("Unexpected API response shape")
    row = data[0]
    price = float(row["price"])
    millis = int(row["millisUTC"])
    return CurrentHourPrice(price_cents=price, millis_utc=millis)


def in_alert_window(now_local: datetime, start_hour: int, end_hour: int) -> bool:
    """Inclusive local clock hours 0–23. If start_hour > end_hour, window wraps past midnight."""
    h = now_local.hour
    if start_hour <= end_hour:
        return start_hour <= h <= end_hour
    return h >= start_hour or h <= end_hour


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return int(str(raw).strip())


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return float(str(raw).strip())


def parse_window_hours() -> tuple[int, int]:
    start = _env_int("ALERT_WINDOW_START_HOUR", DEFAULT_WINDOW_START_HOUR)
    end = _env_int("ALERT_WINDOW_END_HOUR", DEFAULT_WINDOW_END_HOUR)
    for label, v in ("ALERT_WINDOW_START_HOUR", start), ("ALERT_WINDOW_END_HOUR", end):
        if not 0 <= v <= 23:
            raise SystemExit(f"{label} must be 0–23, got {v}")
    return start, end


def send_email_smtp(
    subject: str,
    body: str,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    to_addr: str,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(body)
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)


def send_sms_twilio(
    body: str,
    *,
    session: requests.Session,
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
) -> None:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    session.post(
        url,
        data={"From": from_number, "To": to_number, "Body": body},
        auth=(account_sid, auth_token),
        timeout=30,
    ).raise_for_status()


def main() -> int:
    load_dotenv()

    tz_name = (os.environ.get("COMED_TZ") or "").strip() or "America/Chicago"
    threshold = _env_float("PRICE_THRESHOLD_CENTS", 3.0)
    win_start, win_end = parse_window_hours()

    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)

    if not in_alert_window(now_local, win_start, win_end):
        span = (
            f"{win_start}:00–{win_end}:59"
            if win_start <= win_end
            else f"{win_start}:00–{win_end}:59 (overnight wrap)"
        )
        print(f"Outside alert window ({span} {tz_name}); skipping.")
        return 0

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "comed-pricing-agent/1.0 (personal notifier)",
            "Accept": "application/json",
        }
    )

    try:
        current = fetch_current_hour_average(session)
    except Exception as e:
        print(f"API error: {e}", file=sys.stderr)
        return 1

    hour_key = now_local.strftime("%Y-%m-%d-%H")
    state = load_state()
    last_alert_hour = state.get("last_alert_hour")

    print(
        f"{now_local.isoformat()} | "
        f"current-hour avg: {current.price_cents:.4g} ¢/kWh "
        f"(threshold < {threshold})"
    )

    if current.price_cents >= threshold:
        state["last_price_seen"] = current.price_cents
        save_state(state)
        return 0

    # Below threshold: notify at most once per local clock hour
    if last_alert_hour == hour_key:
        print("Already alerted this hour; skipping duplicate.")
        return 0

    subject = (
        f"ComEd: cheap hour — {current.price_cents:.2f} ¢/kWh (< {threshold})"
    )
    body = (
        f"ComEd current-hour average is {current.price_cents:.2f} ¢/kWh "
        f"(below {threshold} ¢/kWh).\n\n"
        "Good time to start or continue EV charging, dryer, or other heavy loads "
        "if you use hourly rates.\n\n"
        f"Local time: {now_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
        f"API: {API_URL}\n"
    )

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    email_to = os.environ.get("ALERT_EMAIL_TO")

    if smtp_host and smtp_port and smtp_user and smtp_pass and email_to:
        send_email_smtp(
            subject,
            body,
            host=smtp_host,
            port=int(smtp_port),
            user=smtp_user,
            password=smtp_pass,
            to_addr=email_to,
        )
        print("Email sent.")
    else:
        print("SMTP not fully configured; no email sent.")

    tw_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    tw_token = os.environ.get("TWILIO_AUTH_TOKEN")
    tw_from = os.environ.get("TWILIO_FROM_NUMBER")
    tw_to = os.environ.get("ALERT_SMS_TO")

    if tw_sid and tw_token and tw_from and tw_to:
        sms_body = (
            f"ComEd cheap hour: {current.price_cents:.2f} ¢/kWh (<{threshold}). "
            f"EV/heavy loads. {now_local.strftime('%m/%d %I:%M %p %Z')}"
        )
        send_sms_twilio(
            sms_body,
            session=session,
            account_sid=tw_sid,
            auth_token=tw_token,
            from_number=tw_from,
            to_number=tw_to,
        )
        print("SMS sent.")
    else:
        print("Twilio not fully configured; no SMS sent.")

    if not (
        (smtp_host and smtp_port and smtp_user and smtp_pass and email_to)
        or (tw_sid and tw_token and tw_from and tw_to)
    ):
        print(
            "No delivery method configured. Copy .env.example to .env and set SMTP or Twilio.",
            file=sys.stderr,
        )
        return 1

    state["last_alert_hour"] = hour_key
    state["last_price_seen"] = current.price_cents
    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
