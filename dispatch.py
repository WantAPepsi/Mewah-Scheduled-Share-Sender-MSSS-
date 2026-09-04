import asyncio, os
from core import fetch_market_history, load_cfg, send_report, evaluate_eod_readiness, build_report_html

async def main():
    cfg=load_cfg(); rows=await fetch_market_history(); readiness=evaluate_eod_readiness(rows,cfg)
    print(f"JARVIS // EOD readiness: {readiness}")
    if not readiness["ready"]:
        print("JARVIS // No report sent. Provider freshness or scheduling guard blocked dispatch.")
        return
    if os.getenv("JARVIS_DRY_RUN","0") == "1":
        print(f"JARVIS // DRY RUN: report type={readiness.get('report_type')}; email step intentionally skipped.")
        print(build_report_html(rows,cfg,readiness)[:700]); return
    send_report(rows,cfg,readiness)
    print("JARVIS // Daily Mewah report dispatched successfully.")

if __name__=="__main__":
    asyncio.run(main())
