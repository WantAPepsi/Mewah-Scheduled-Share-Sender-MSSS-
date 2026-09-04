from __future__ import annotations
import asyncio, json, os
from datetime import datetime
from pathlib import Path
from core import SGT, fetch_market_history

OUT = Path(__file__).resolve().parent / "probe_results"

async def main():
    now = datetime.now(SGT)
    today = now.strftime("%Y-%m-%d")
    checked_at = now.isoformat(timespec="seconds")
    try:
        rows = await fetch_market_history()
        latest = rows[0] if rows else None
        latest_date = latest.get("date_iso") if latest else None
        same_day = bool(latest and latest_date == today)
        result = {
            "checked_at_sgt": checked_at,
            "today_sgt": today,
            "latest_market_date": latest_date,
            "same_day_row_available": same_day,
            "provider_symbol": latest.get("provider_symbol") if latest else None,
            "latest_open": latest.get("open") if latest else None,
            "latest_close": latest.get("close") if latest else None,
            "latest_volume": latest.get("volume") if latest else None,
            "status": "SAME_DAY_AVAILABLE" if same_day else "NOT_YET_AVAILABLE",
        }
    except Exception as exc:
        result = {
            "checked_at_sgt": checked_at,
            "today_sgt": today,
            "latest_market_date": None,
            "same_day_row_available": False,
            "status": "ERROR",
            "error": str(exc),
        }

    OUT.mkdir(exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S_SGT")
    path = OUT / f"marketstack_probe_{stamp}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("JARVIS // MARKETSTACK PUBLICATION PROBE")
    print(json.dumps(result, indent=2))
    print(f"JARVIS // Probe result written to {path}")

if __name__ == "__main__":
    asyncio.run(main())
