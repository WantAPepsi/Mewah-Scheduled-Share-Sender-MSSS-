from __future__ import annotations
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from core import CFG, load_cfg, fetch_market_history, provider_diagnostic, send_report, build_report_html, evaluate_eod_readiness

app=FastAPI(title="JARVIS Mewah Share Monitor")

def save_cfg(c):
    CFG.write_text(json.dumps(c,indent=2),encoding="utf-8")

class ReportConfig(BaseModel):
    sender_name:str=""
    sender_email:str=""
    to:str=""
    cc:str=""
    send_time:str="18:30"
    weekday_only:bool=True

@app.get("/",response_class=HTMLResponse)
def home(): return INDEX

@app.get("/api/config")
def cfg(): return load_cfg()


@app.get("/api/provider-diagnostic")
async def provider_diag():
    try:
        return await provider_diagnostic()
    except Exception as e:
        raise HTTPException(500,str(e))

@app.get("/api/history")
async def history():
    try:
        c=load_cfg(); rows=await fetch_market_history()
        return {"rows":rows,"source":c.get("data_source",{}).get("label","Configured provider"),"symbol":c["stock"]["symbol"]}
    except Exception as e:
        raise HTTPException(500,str(e))

@app.get("/api/readiness")
async def readiness():
    try:
        c=load_cfg(); rows=await fetch_market_history()
        return evaluate_eod_readiness(rows,c)
    except Exception as e:
        raise HTTPException(500,str(e))

@app.get("/api/report-preview",response_class=HTMLResponse)
async def report_preview():
    try:
        c=load_cfg(); rows=await fetch_market_history(); return build_report_html(rows,c)
    except Exception as e:
        raise HTTPException(500,str(e))

@app.post("/api/report-config")
def report_config(x:ReportConfig):
    c=load_cfg(); r=c["report"]
    r["sender_name"]=x.sender_name.strip(); r["sender_email"]=x.sender_email.strip()
    r["to"]=[a.strip() for a in x.to.split(",") if a.strip()]
    r["cc"]=[a.strip() for a in x.cc.split(",") if a.strip()]
    r["send_time"]=x.send_time.strip() or "18:30"; r["weekday_only"]=x.weekday_only
    save_cfg(c)
    return {"ok":True}

@app.post("/api/send-email")
async def send_email():
    try:
        c=load_cfg(); rows=await fetch_market_history(); send_report(rows,c); return {"ok":True}
    except Exception as e:
        raise HTTPException(500,str(e))

INDEX=r'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>JARVIS Mewah Share Monitor</title>
<style>
:root{--bg:#050b12;--panel:#08131f;--line:#17384f;--cyan:#78e7ff;--text:#eef8ff;--muted:#89a8b8;--green:#55e6a5;--red:#ff8a80;--amber:#ffc857}
*{box-sizing:border-box}body{margin:0;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial;background:radial-gradient(circle at 20% 0%,rgba(22,185,223,.1),transparent 34%),var(--bg)}
.shell{max-width:1400px;margin:auto;padding:22px}.topbar{display:flex;justify-content:space-between;align-items:center;border:1px solid var(--line);background:#08131f;padding:18px 20px;border-radius:18px}.brand{font-size:12px;color:var(--cyan);letter-spacing:2.4px}.pill{border:1px solid rgba(85,230,165,.35);color:var(--green);padding:9px 12px;border-radius:999px;font-size:13px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}.stat,.card{background:#08131f;border:1px solid var(--line);border-radius:16px;padding:16px}.label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:1px}.value{font-size:23px;font-weight:800;margin-top:7px}.grid{display:grid;grid-template-columns:1.8fr .8fr;gap:16px}
button{border:1px solid #1b526a;background:#0b2738;color:white;font-weight:700;border-radius:10px;padding:11px 14px;cursor:pointer}button.primary{background:#0b4c68;border-color:#1b8fb7}input{width:100%;background:#06111b;color:white;border:1px solid #17384f;border-radius:10px;padding:11px 12px;font-size:15px;margin:5px 0 11px}label{display:block;color:var(--muted);font-size:12px;margin-top:9px}
.tablewrap{max-height:650px;overflow:auto;border:1px solid #113247;border-radius:12px}table{width:100%;border-collapse:collapse;font-size:13px}th{background:#0c2a3d;color:#bdefff;padding:10px;position:sticky;top:0}td{padding:9px;border-bottom:1px solid #123044}.num{text-align:right}.latest td{background:rgba(255,178,74,.1)}
.console{margin-top:14px;background:#03080d;border:1px solid #133044;border-radius:12px;padding:12px;font-family:Consolas,monospace;color:#88dff4;font-size:12px;min-height:70px}.cloudbox{margin-top:14px;border:1px solid #174961;background:#071825;padding:12px;border-radius:12px}.ready{color:var(--green)}.waiting{color:var(--amber)}@media(max-width:900px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}
</style></head><body><div class="shell">
<div class="topbar"><div><div class="brand">JARVIS MARKET INTELLIGENCE // MARK X</div><h1>Mewah Share Monitor</h1></div><div class="pill">TIMING CALIBRATION</div></div>
<div class="stats"><div class="stat"><div class="label">Latest Close</div><div id="latestClose" class="value">—</div></div><div class="stat"><div class="label">Daily Move</div><div id="dailyMove" class="value">—</div></div><div class="stat"><div class="label">Latest Volume</div><div id="latestVolume" class="value">—</div></div><div class="stat"><div class="label">EOD Schedule</div><div class="value" style="font-size:16px">18:30 SGT · Mon–Fri</div></div></div>
<div class="grid"><div class="card"><h2>Share Movement Intelligence</h2><p style="color:#89a8b8">MV4 · SGX · Marketstack end-of-day feed</p><button class="primary" onclick="runDiagnostic()">Test Marketstack coverage</button> <button onclick="loadHistory()">Refresh market data</button> <button onclick="window.open('/api/report-preview','_blank')">Preview email</button><div class="tablewrap" style="margin-top:14px"><table><thead><tr><th>Date</th><th>Opening Share Price (SGD)</th><th>Closing Share Price (SGD)</th><th>Transaction Volume</th><th>Remarks</th></tr></thead><tbody id="rows"></tbody></table></div></div>
<div class="card"><h2>Dispatch Control</h2><div class="cloudbox"><b>End-of-day guard</b><p id="readiness" class="waiting" style="font-size:13px">Checking today's completed data…</p></div>
<label>Sender name</label><input id="sender_name" placeholder="Mewah Share Monitor"><label>Sender email</label><input id="sender_email" placeholder="sender@company.com"><label>To recipients — comma separated</label><input id="to"><label>CC recipients — comma separated</label><input id="cc"><label>Target send time (Singapore)</label><input id="send_time" value="18:30">
<button class="primary" onclick="saveCfg()">Save configuration</button> <button onclick="sendMail()">Send test email</button>
<div class="cloudbox"><b>Cloud mode</b><p style="color:#89a8b8;font-size:13px">Automatic run: 18:30 SGT. JARVIS will not send yesterday's row as today's report; if the provider has not published today's row yet, the run safely skips and can be re-run manually.</p></div>
<div class="cloudbox"><b>Data source</b><p style="color:#89a8b8;font-size:13px">Primary connector: Marketstack EOD API. MARK X uses the verified Marketstack MV4.SI/XSES feed. Cloud timing calibration checks when each trading day's EOD row becomes available. If today has no new MV4 row, JARVIS sends a clearly labelled no-new-row notice for a one-weekday gap; larger gaps are treated as provider freshness failures and blocked. The API key stays server-side in .env.</p></div><div id="console" class="console">JARVIS // Ready.</div></div></div></div>
<script>
const $=id=>document.getElementById(id);
async function init(){try{const c=await fetch('/api/config').then(r=>r.json()),x=c.report;$('sender_name').value=x.sender_name||'';$('sender_email').value=x.sender_email||'';$('to').value=(x.to||[]).join(', ');$('cc').value=(x.cc||[]).join(', ');$('send_time').value=x.send_time||'18:30';if(c.data_source&&c.data_source.marketstack_resolved_symbol){logMsg('Verified provider symbol already saved: '+c.data_source.marketstack_resolved_symbol+'. Loading market data...');await loadHistory();await loadReadiness()}else{logMsg('Ready. Click Test Marketstack coverage. JARVIS will probe MV4 symbol formats and only save one that returns XSES data.')}}catch(e){logMsg('Initialization failed: '+e.message,true)}}
async function runDiagnostic(){logMsg('Probing Marketstack for Mewah across MV4 symbol formats...');try{const r=await fetch('/api/provider-diagnostic'),j=await r.json();if(!r.ok){logMsg(j.detail||'Diagnostic failed.',true);return}const tries=(j.attempts||[]).map(x=>x.ok?`${x.candidate}: ${x.rows} rows [${(x.exchanges||[]).join(',')||'no exchange'}]`:`${x.candidate}: rejected`).join(' | ');if(j.success){logMsg(`✓ SGX:MV4 VERIFIED — provider symbol ${j.resolved_symbol}; ${j.sgx_eod_rows} XSES row(s). ${tries}`);await loadHistory();await loadReadiness()}else{logMsg(`✗ No XSES data found. ${tries}`,true)}}catch(e){logMsg('Diagnostic error: '+e.message,true)}}
async function loadHistory(){logMsg('Testing Marketstack for MV4 on SGX/XSES and acquiring EOD data...');try{const r=await fetch('/api/history'),j=await r.json();if(!r.ok){logMsg(j.detail||'Market data request failed.',true);return}const d=(j.rows||[]).slice(0,40),tbody=$('rows');tbody.innerHTML='';d.forEach((x,i)=>tbody.insertAdjacentHTML('beforeend',`<tr class="${i===0?'latest':''}"><td>${x.date}</td><td class="num">${Number(x.open).toFixed(3)}</td><td class="num">${Number(x.close).toFixed(3)}</td><td class="num">${Number(x.volume).toLocaleString()}</td><td>${x.remarks||''}</td></tr>`));if(d.length){$('latestClose').textContent='S$'+Number(d[0].close).toFixed(3);$('latestVolume').textContent=Number(d[0].volume).toLocaleString();if(d[1]&&d[1].close){const p=(d[0].close-d[1].close)/d[1].close*100;$('dailyMove').textContent=(p>=0?'+':'')+p.toFixed(2)+'%'}logMsg(`Market data synchronized. ${j.symbol} via ${j.source}${d[0].provider_symbol?' ['+d[0].provider_symbol+']':''}.`)}else logMsg('No market rows were returned.',true)}catch(e){logMsg('Market data error: '+e.message,true)}}
async function loadReadiness(){try{const r=await fetch('/api/readiness'),j=await r.json(),el=$('readiness');el.textContent=(j.ready?'READY — ':'WAITING — ')+j.reason;el.className=j.ready?'ready':'waiting'}catch(e){$('readiness').textContent='Readiness check failed: '+e.message}}
async function saveCfg(){const p={sender_name:$('sender_name').value,sender_email:$('sender_email').value,to:$('to').value,cc:$('cc').value,send_time:$('send_time').value,weekday_only:true};try{const r=await fetch('/api/report-config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)}),j=await r.json();logMsg(r.ok?'Configuration saved locally. Email authentication can be added later.':(j.detail||'Could not save configuration.'),!r.ok)}catch(e){logMsg('Configuration error: '+e.message,true)}}
async function sendMail(){logMsg('Attempting test report...');try{const r=await fetch('/api/send-email',{method:'POST'}),j=await r.json();logMsg(r.ok?'Test email sent successfully.':(j.detail||'Email dispatch failed.'),!r.ok)}catch(e){logMsg('Email error: '+e.message,true)}}
function logMsg(t,e=false){const el=$('console');el.textContent='JARVIS // '+t;el.style.color=e?'#ff8a80':'#55e6a5'}init();
</script></body></html>'''
