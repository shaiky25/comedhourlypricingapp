# ComEd hourly pricing notifier

Small Python utility that checks ComEd’s **current-hour average** price ([API](https://hourlypricing.comed.com/api?type=currenthouraverage)) and sends you **email** and/or **SMS** when the price drops below a limit you set, during hours you choose. Handy if you’re on **Hourly Pricing** and want a nudge to run an **EV charge**, **dryer**, or other heavy loads when the hour is cheap.

This project is **not** affiliated with ComEd or Exelon. It only reads the public API.

---

## What you need

- **Python 3.9+** (3.11 recommended)
- An email account that supports **SMTP** (e.g. Gmail with an [app password](https://support.google.com/accounts/answer/185833)), and/or a **[Twilio](https://www.twilio.com/)** account for SMS
- Optional: a **[GitHub](https://github.com/)** account if you want it to run in the cloud on a schedule

---

## After you download the project

1. Open a terminal and go to the folder that contains `comed_pricing_agent.py` (the project root).

2. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Copy the environment template and edit it:

   ```bash
   cp .env.example .env
   ```

   Open `.env` in an editor. Set at least one delivery path:

   - **Email:** fill in `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `ALERT_EMAIL_TO`.
   - **SMS:** fill in `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, and `ALERT_SMS_TO`.

   Adjust behavior if you want:

   | Variable | Purpose |
   |----------|---------|
   | `COMED_TZ` | Timezone for the alert window (default `America/Chicago`). |
   | `PRICE_THRESHOLD_CENTS` | Notify when the **current-hour average** is **strictly below** this value (¢/kWh). Default `3`. |
   | `ALERT_WINDOW_START_HOUR` / `ALERT_WINDOW_END_HOUR` | Local hours `0`–`23` when alerts are allowed. If start \> end, the window **wraps** past midnight (e.g. `22` and `6` = 10 PM–6 AM). Defaults `5` and `23` (5 AM–11 PM). |

4. Run once to verify:

   ```bash
   source .venv/bin/activate
   python comed_pricing_agent.py
   ```

   You should see a line with the current hour average and your threshold. **Email/SMS only send** when the price is **below** the threshold **and** you’re inside the alert window. If nothing sends, the hour may simply be above your limit.

---

## Run automatically on your computer

Your machine needs to be on (and ideally awake) when the job runs.

**cron (Mac/Linux)** — edit with `crontab -e` and add (fix the path to your project):

```text
*/10 * * * * cd "/path/to/Comed App" && .venv/bin/python comed_pricing_agent.py >> /tmp/comed-agent.log 2>&1
```

**Windows:** use **Task Scheduler** to run the same `python comed_pricing_agent.py` from the project folder with the venv’s `python.exe`, on a repeating interval.

The script writes `.comed_notifier_state.json` in the project folder so you get **at most one alert per local clock hour** when price stays under the threshold (avoids spam if you run every few minutes).

---

## Run in the cloud (GitHub Actions)

If you **push this repo to GitHub** (use a **private** repo; do **not** commit `.env`):

1. Add **repository secrets** under **Settings → Secrets and variables → Actions** using the **same names** as in `.env.example` (`SMTP_*`, `TWILIO_*`, `COMED_TZ`, etc.).
2. The workflow **`.github/workflows/comed-pricing.yml`** runs on a schedule and restores notifier state via **Actions cache** so dedup still works.

You can trigger a manual run from the **Actions** tab (**Run workflow**).

---

## Files to know

| File | Role |
|------|------|
| `comed_pricing_agent.py` | Main script |
| `.env.example` | Template for secrets and settings |
| `.env` | Your real config (gitignored) |
| `.comed_notifier_state.json` | Last-alert bookkeeping (gitignored) |
| `requirements.txt` | Python dependencies |

---

## Troubleshooting

- **No email/SMS:** Price may be above the threshold, or you’re **outside** `ALERT_WINDOW_*`. Check the printed line when you run manually.
- **Gmail blocks login:** Use an **app password**, not your normal password; ensure **less secure app** / 2FA rules match Google’s current docs.
- **Twilio SMS fails:** Trial accounts can only message **verified** numbers; check the Twilio error in the Actions log or terminal.
- **“No delivery method configured”:** Fill in **all** fields for either SMTP or Twilio in `.env` (or GitHub secrets).

---

## License

Use and modify for personal use. ComEd and related marks belong to their owners.
