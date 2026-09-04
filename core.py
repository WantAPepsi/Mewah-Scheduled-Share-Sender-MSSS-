from __future__ import annotations
import json, os, smtplib, statistics
from datetime import datetime, time, timedelta
from pathlib import Path
from email.message import EmailMessage
from zoneinfo import ZoneInfo
import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).resolve().parent
CFG = BASE / "config.json"
SGT = ZoneInfo("Asia/Singapore")
MARKETSTACK_BASE = "https://api.marketstack.com/v2"


def load_cfg():
    return json.loads(CFG.read_text(encoding="utf-8"))


def parse_hhmm(value: str) -> time:
    h, m = (int(x) for x in value.split(":", 1))
    return time(h, m)


def _marketstack_error(payload) -> str:
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or err)
        if err:
            return str(err)
        return str(payload.get("message") or payload.get("detail") or payload)
    return str(payload)


async def _get_json(client: httpx.AsyncClient, path: str, params: dict):
    r = await client.get(f"{MARKETSTACK_BASE}{path}", params=params)
    try:
        payload = r.json()
    except Exception as exc:
        detail = r.text[:400].strip()
        raise RuntimeError(f"Marketstack returned a non-JSON response ({r.status_code}): {detail}") from exc
    if r.status_code == 429:
        raise RuntimeError("Marketstack rate limit reached. Wait for the monthly/request allowance to reset, then retry.")
    if r.status_code in (401, 403):
        raise RuntimeError(f"Marketstack rejected the API key or plan: {_marketstack_error(payload)}")
    if r.status_code >= 400 or (isinstance(payload, dict) and payload.get("error")):
        raise RuntimeError(f"Marketstack API error: {_marketstack_error(payload)}")
    return payload


async def _probe_marketstack_candidates(client: httpx.AsyncClient, token: str, symbol: str, target_mic: str, date_from: str):
    candidates = []
    for cand in (symbol, f"{symbol}.{target_mic}", f"{symbol}:{target_mic}", f"{symbol}.SI"):
        if cand not in candidates:
            candidates.append(cand)
    attempts = []
    for cand in candidates:
        try:
            payload = await _get_json(client, "/eod", {
                "access_key": token,
                "symbols": cand,
                "date_from": date_from,
                "limit": 25,
                "sort": "DESC",
            })
            rows = (payload.get("data") or []) if isinstance(payload, dict) else []
            exchanges = sorted({str(x.get("exchange") or "").upper() for x in rows if isinstance(x, dict) and x.get("exchange")})
            xses_rows = [x for x in rows if isinstance(x, dict) and str(x.get("exchange") or "").upper() == target_mic]
            attempts.append({"candidate": cand, "ok": True, "rows": len(rows), "exchanges": exchanges, "xses_rows": len(xses_rows)})
            if xses_rows:
                return cand, xses_rows, attempts
        except Exception as exc:
            attempts.append({"candidate": cand, "ok": False, "error": str(exc)})
    return None, [], attempts


async def provider_diagnostic():
    token = os.getenv("MARKETSTACK_API_KEY", "").strip()
    if not token:
        raise RuntimeError(
            "MARKETSTACK_API_KEY is missing. Create a .env file beside app.py and add "
            "MARKETSTACK_API_KEY=your_key_here, then restart JARVIS."
        )

    c = load_cfg()
    ds = c.get("data_source", {})
    symbol = str(ds.get("marketstack_symbol") or "MV4").strip().upper()
    target_mic = str(ds.get("marketstack_mic") or "XSES").strip().upper()
    date_from = (datetime.now(SGT).date() - timedelta(days=int(ds.get("history_days", 220)))).isoformat()
    ticker_matches = []
    ticker_errors = []

    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers={"User-Agent":"JARVIS-Mewah-Share-Monitor/10.1"}) as client:
        for path, params in [
            (f"/tickers/{symbol}", {"access_key": token}),
            ("/tickers", {"access_key": token, "search": symbol, "limit": 100}),
        ]:
            try:
                payload = await _get_json(client, path, params)
                raw = payload.get("data") if isinstance(payload, dict) else None
                items = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    stock_exchange = item.get("stock_exchange") if isinstance(item.get("stock_exchange"), dict) else {}
                    mic = str(stock_exchange.get("mic") or item.get("exchange") or item.get("mic") or "").upper()
                    ticker_matches.append({
                        "symbol": str(item.get("symbol") or "").upper(),
                        "name": item.get("name") or item.get("company_name") or "",
                        "exchange_name": stock_exchange.get("name") or stock_exchange.get("acronym") or item.get("exchange") or "",
                        "mic": mic,
                        "country": stock_exchange.get("country") or item.get("country") or "",
                    })
            except Exception as exc:
                ticker_errors.append(str(exc))

        resolved, xses_rows, attempts = await _probe_marketstack_candidates(client, token, symbol, target_mic, date_from)

    if resolved:
        c["data_source"]["marketstack_resolved_symbol"] = resolved
        c["stock"]["provider_symbol"] = f"{resolved} ({target_mic})"
        CFG.write_text(json.dumps(c, indent=2), encoding="utf-8")
        return {
            "provider": "Marketstack",
            "symbol": symbol,
            "target_mic": target_mic,
            "ticker_matches": ticker_matches,
            "ticker_errors": ticker_errors,
            "attempts": attempts,
            "resolved_symbol": resolved,
            "sgx_eod_rows": len(xses_rows),
            "success": True,
            "message": f"Verified {resolved}: Marketstack returned {len(xses_rows)} XSES EOD row(s). Saved as the provider symbol."
        }

    return {
        "provider": "Marketstack",
        "symbol": symbol,
        "target_mic": target_mic,
        "ticker_matches": ticker_matches,
        "ticker_errors": ticker_errors,
        "attempts": attempts,
        "resolved_symbol": None,
        "sgx_eod_rows": 0,
        "success": False,
        "message": "No tested Marketstack symbol form returned XSES/SGX EOD data for Mewah."
    }


async def fetch_market_history():
    c = load_cfg()
    provider = c.get("data_source", {}).get("provider", "marketstack")
    if provider != "marketstack":
        raise RuntimeError(f"Unsupported data provider: {provider}")
    return await _fetch_marketstack(c)


async def _fetch_marketstack(c):
    token = os.getenv("MARKETSTACK_API_KEY", "").strip()
    if not token:
        raise RuntimeError(
            "MARKETSTACK_API_KEY is missing. Create a .env file beside app.py and add "
            "MARKETSTACK_API_KEY=your_key_here, then restart JARVIS."
        )

    ds = c.get("data_source", {})
    target_mic = str(ds.get("marketstack_mic") or "XSES").strip().upper()
    # Cloud runners are stateless, so never depend on a locally-saved diagnostic result.
    # MV4.SI was verified against Marketstack as the Mewah listing returning MIC XSES.
    # Every fetch below still rejects any row whose exchange is not XSES.
    resolved_symbol = str(ds.get("marketstack_resolved_symbol") or "MV4.SI").strip()

    date_from = (datetime.now(SGT).date() - timedelta(days=int(ds.get("history_days", 220)))).isoformat()
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers={"User-Agent":"JARVIS-Mewah-Share-Monitor/10.1"}) as client:
        payload = await _get_json(client, "/eod", {
            "access_key": token,
            "symbols": resolved_symbol,
            "date_from": date_from,
            "limit": 100,
            "sort": "DESC",
        })

    values = (payload.get("data") or []) if isinstance(payload, dict) else []
    if not values:
        raise RuntimeError(f"Marketstack returned no EOD rows for verified provider symbol {resolved_symbol}.")

    exchanges = sorted({str(x.get("exchange") or "").upper() for x in values if isinstance(x, dict) and x.get("exchange")})
    values = [x for x in values if isinstance(x, dict) and str(x.get("exchange") or "").upper() == target_mic]
    if not values:
        raise RuntimeError(
            f"Marketstack stopped returning XSES rows for verified symbol {resolved_symbol}. "
            f"Exchanges returned: {', '.join(exchanges) if exchanges else 'none'}. JARVIS refused the data."
        )

    rows = []
    for item in values:
        try:
            raw_date = str(item.get("date") or "")
            date_iso = raw_date[:10]
            dt = datetime.strptime(date_iso, "%Y-%m-%d")
            o, cl = item.get("open"), item.get("close")
            if o in (None, "") or cl in (None, ""):
                continue
            volume_raw = item.get("volume")
            volume = int(float(volume_raw)) if volume_raw not in (None, "") else 0
            rows.append({
                "date": dt.strftime("%d-%b-%y").lstrip("0"),
                "date_iso": date_iso,
                "open": float(o),
                "high": float(item["high"]) if item.get("high") not in (None, "") else None,
                "low": float(item["low"]) if item.get("low") not in (None, "") else None,
                "close": float(cl),
                "volume": volume,
                "remarks": "",
                "provider_symbol": f"{resolved_symbol}:{target_mic}",
            })
        except (TypeError, ValueError):
            continue

    rows.sort(key=lambda x: x["date_iso"], reverse=True)
    if not rows:
        raise RuntimeError("Marketstack returned XSES records, but no usable OHLC rows were found.")
    return apply_remarks(rows, {}, c)

def _with_liquidity_note(text: str, row: dict, rules: dict) -> str:
    if not rules.get("annotate_low_volume_moves", True):
        return text
    threshold = int(rules.get("low_volume_threshold", 50000))
    if 0 < row.get("volume", 0) < threshold:
        return f"{text} on low volume ({row['volume']:,})"
    return text


def apply_remarks(rows, dividend_events, cfg):
    rules=cfg["remarks_rules"]
    lookback=int(rules.get("new_high_low_lookback",20))
    for i,row in enumerate(rows):
        notes=[]
        trailing=rows[i+1:i+21]
        vols=[x["volume"] for x in trailing if x.get("volume",0)>0]
        med=statistics.median(vols) if vols else 0
        if row["volume"]==0 and rules.get("show_zero_volume",True):
            notes.append("No recorded trading volume")
        elif med and row["volume"]>=med*float(rules["volume_spike_multiplier"]) and row["volume"]>=int(rules["volume_spike_minimum"]):
            notes.append(f"Volume spike ({row['volume']/med:.1f}× 20-day median)")
        if i+1<len(rows) and rows[i+1]["close"]:
            prev=rows[i+1]["close"]
            move=(row["close"]-prev)/prev*100
            if abs(move)>=float(rules["large_close_move_percent"]):
                text=f"Large daily {'rise' if move>0 else 'fall'} ({move:+.1f}%)"
                notes.append(_with_liquidity_note(text,row,rules))
        if row["open"]:
            intra=(row["close"]-row["open"])/row["open"]*100
            if abs(intra)>=float(rules["large_intraday_move_percent"]):
                text=f"Strong intraday {'gain' if intra>0 else 'drop'} ({intra:+.1f}%)"
                notes.append(_with_liquidity_note(text,row,rules))
        older=rows[i+1:i+1+lookback]
        if len(older)>=min(10,lookback):
            cls=[x["close"] for x in older if x.get("close") is not None]
            if cls:
                if row["close"]>max(cls): notes.append(f"New {lookback}-session closing high")
                elif row["close"]<min(cls): notes.append(f"New {lookback}-session closing low")
        if rules.get("show_dividend_events",True) and row["date_iso"] in dividend_events:
            notes.append(f"Dividend event: SGD {dividend_events[row['date_iso']]:.4f}/share")
        row["remarks"]="; ".join(notes)
    return rows


def _weekday_gap(start_iso: str, end_iso: str) -> int:
    """Count weekdays after start_iso through end_iso, ignoring weekends."""
    start = datetime.strptime(start_iso, "%Y-%m-%d").date()
    end = datetime.strptime(end_iso, "%Y-%m-%d").date()
    if end <= start:
        return 0
    days = 0
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def evaluate_eod_readiness(rows, cfg, now=None):
    now = now or datetime.now(SGT)
    rep = cfg["report"]
    today = now.strftime("%Y-%m-%d")
    latest = rows[0] if rows else None
    result = {
        "ready": False,
        "report_type": "blocked",
        "today": today,
        "latest_market_date": latest.get("date_iso") if latest else None,
        "reason": "",
        "checked_at": now.isoformat(timespec="seconds"),
    }
    if not rows:
        result["reason"] = "No market data available."
        return result
    if rep.get("weekday_only", True) and now.weekday() >= 5:
        result["reason"] = "Weekend: no scheduled report."
        return result
    earliest = parse_hhmm(rep.get("earliest_send_time", "17:15"))
    if now.time() < earliest:
        result["reason"] = f"Too early for end-of-day dispatch; earliest is {earliest.strftime('%H:%M')} SGT."
        return result

    latest_iso = latest.get("date_iso")
    if latest_iso == today:
        if latest.get("open") is None or latest.get("close") is None:
            result["reason"] = "Today's OHLC data is incomplete."
            return result
        result["ready"] = True
        result["report_type"] = "normal"
        result["reason"] = "Completed current-day row is available."
        return result

    # No current-day row. A one-weekday gap is treated as a dispatchable
    # "no new MV4 row" notice, not as proof that no trades occurred.
    try:
        gap = _weekday_gap(latest_iso, today) if latest_iso else 999
    except Exception:
        gap = 999
    result["weekday_gap"] = gap

    if rep.get("require_current_trading_day", True):
        if gap == 1 and rep.get("send_no_new_row_notice", True):
            result["ready"] = True
            result["report_type"] = "no_new_row"
            result["reason"] = (
                f"No new MV4 EOD row is published for {today}; latest available session is {latest_iso}. "
                "JARVIS will send a no-new-row notice rather than reuse the old row as today's data."
            )
            return result
        result["reason"] = (
            f"Provider freshness alert: latest MV4 row is {latest_iso}, {gap} weekday(s) behind {today}. "
            "JARVIS will not send a daily report until fresh data is available."
        )
        return result

    result["ready"] = True
    result["report_type"] = "historical"
    result["reason"] = f"Current-day row not required; latest available session is {latest_iso}."
    return result


def build_report_html(rows,cfg, readiness=None):
    limit=int(cfg.get("report",{}).get("history_rows",40))
    body=""
    for i,r in enumerate(rows[:limit]):
        bg="#fff36a" if i==0 else "#ffffff"
        weight="700" if i==0 else "400"
        body += (
            f'<tr style="background:{bg};font-weight:{weight}">'
            f'<td style="padding:8px;border:1px solid #c9ced6">{r["date"]}</td>'
            f'<td style="padding:8px;border:1px solid #c9ced6;text-align:right">{r["open"]:.3f}</td>'
            f'<td style="padding:8px;border:1px solid #c9ced6;text-align:right">{r["close"]:.3f}</td>'
            f'<td style="padding:8px;border:1px solid #c9ced6;text-align:right">{r["volume"]:,}</td>'
            f'<td style="padding:8px;border:1px solid #c9ced6">{r["remarks"]}</td></tr>'
        )
    source=cfg.get("data_source",{}).get("label","Configured market-data source")
    provider_symbol=(rows[0].get("provider_symbol") if rows else cfg["stock"]["symbol"])
    readiness = readiness or evaluate_eod_readiness(rows, cfg)
    notice = ""
    if readiness.get("report_type") == "no_new_row":
        today_pretty = datetime.strptime(readiness["today"], "%Y-%m-%d").strftime("%d %b %Y").lstrip("0")
        latest_pretty = datetime.strptime(readiness["latest_market_date"], "%Y-%m-%d").strftime("%d %b %Y").lstrip("0")
        notice = (
            f'<div style="margin:0 0 14px;padding:12px 14px;border:1px solid #d7a300;background:#fff6cc">'
            f'<b>No new MV4 EOD row published for {today_pretty}.</b> '
            f'Latest available traded session remains {latest_pretty}. '
            'This indicates that Marketstack has not published a new MV4 row for today; it is not treated as proof that no trades occurred. '
            'JARVIS has therefore not reused the previous row as today\'s data.'
            '</div>'
        )
    return f"""<html><body style="font-family:Arial,sans-serif;color:#111">
{notice}
<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
<tr><td colspan="5" style="background:#081a2b;color:#7de7ff;font-weight:700;font-size:22px;text-align:center;padding:14px">{cfg['report']['title']}</td></tr>
<tr style="background:#0f3451;color:white"><th>Date</th><th>Opening Share Price (SGD)</th><th>Closing Share Price (SGD)</th><th>Transaction Volume</th><th>Remarks</th></tr>
{body}</table>
<p style="font-size:12px;color:#666">Source: {source} for {provider_symbol} / SGX:MV4. Currency: SGD. Automated remarks are indicators for review, not investment advice.</p>
</body></html>"""


def send_report(rows,cfg, readiness=None):
    rep=cfg["report"]
    readiness = readiness or evaluate_eod_readiness(rows, cfg)
    host=os.getenv("SMTP_HOST","smtp.office365.com")
    port=int(os.getenv("SMTP_PORT","587"))
    user=os.getenv("SMTP_USERNAME")
    pwd=os.getenv("SMTP_PASSWORD")
    sender=rep.get("sender_email") or user
    if not all([host,user,pwd,sender,rep.get("to")]):
        raise RuntimeError("Email authentication/recipients are not configured yet. Marketstack market-data and EOD logic are ready.")
    now=datetime.now(SGT)
    msg=EmailMessage()
    msg["From"]=f"{rep.get('sender_name','')} <{sender}>" if rep.get("sender_name") else sender
    msg["To"]=', '.join(rep["to"])
    if rep.get("cc"): msg["Cc"]=', '.join(rep["cc"])
    suffix = " — No new MV4 row" if readiness.get("report_type") == "no_new_row" else ""
    msg["Subject"]=f"Mewah Share Movement_{now.strftime('%d %b %Y').lstrip('0')} ({now.strftime('%A')}){suffix}"
    msg.set_content("Mewah Share Movement report")
    msg.add_alternative(build_report_html(rows,cfg,readiness),subtype="html")
    with smtplib.SMTP(host,port,timeout=30) as s:
        s.starttls()
        s.login(user,pwd)
        s.send_message(msg)
