# JARVIS Mark X — Marketstack publication timing calibration

Mark X keeps the verified `MV4.SI` / `XSES` Marketstack connector from Mark IX.2 and adds a cloud timing probe.

## What it does

During calibration, GitHub Actions checks Marketstack at **17:30, 18:30, 19:30 and 20:30 Singapore time, Monday-Friday**. Each run records whether the current Singapore date is already available as the latest MV4 EOD row. The result is uploaded as a small JSON artifact and printed in the Actions log.

The normal automatic email schedule is deliberately disabled while timing is being measured. `daily-report.yml` remains available as a manual dry run only.

## GitHub setup

1. Create a **private** GitHub repository and upload/push the contents of this folder. Do not upload `.env`.
2. In **Settings → Secrets and variables → Actions → Secrets**, add:
   - `MARKETSTACK_API_KEY` = your Marketstack key
3. In **Variables**, add:
   - `JARVIS_PROBE_ENABLED` = `1`
4. Go to **Actions → Marketstack MV4 Publication Timing Probe → Run workflow** once manually to confirm it works.
5. Leave it running for a few SGX trading days. Each scheduled run produces an artifact named `mv4-publication-probe-...` and logs either `SAME_DAY_AVAILABLE` or `NOT_YET_AVAILABLE`.
6. After enough observations, set `JARVIS_PROBE_ENABLED` = `0` to stop consuming Marketstack requests. Then set the permanent report time based on the observed publication window.

## Local `.env`

```env
MARKETSTACK_API_KEY=YOUR_KEY_HERE

SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
```

Email remains unconfigured for now.

## Request budget

Four weekday probes are about 80–92 requests in a typical month, before manual tests. This is close to a 100-request free allowance, so use this only as a short calibration period and disable it afterward.

Do not create extra accounts/API keys just to bypass a provider's quota unless Marketstack explicitly permits that usage. For production, use a plan/licence appropriate for Mewah's internal business use.
