"""Static, credential-free development console; no trading or billing controls."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["development-console"])

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ntfyconnector • Demo Console</title>
<style>
:root { color-scheme: dark; font-family: system-ui, sans-serif }
body { background:#101827; color:#e9eef8; max-width:900px; margin:32px auto; padding:0 20px }
section { padding:20px; border:1px solid #334155; border-radius:12px; margin-bottom:20px }
label { display:block; margin:14px 0 6px }
input,textarea,button { box-sizing:border-box; width:100%; padding:11px; border-radius:6px; font:inherit }
input,textarea { background:#18253b; border:1px solid #475569; color:inherit }
button { background:#3761b8; color:white; border:0; cursor:pointer; margin-top:12px }
button:disabled { opacity:.5; cursor:not-allowed }
small { color:#a9b8d2 }
table { width:100%; border-collapse:collapse; font-size:13px; word-break:break-all }
th,td { text-align:left; padding:9px; border-bottom:1px solid #334155 }
output { display:block; white-space:pre-wrap; margin-top:12px }
</style>
</head>
<body>
<h1>ntfyconnector demo console</h1>
<p>Development only. Order execution is not controlled by this page.</p>
<section>
<h2>Tenant credentials</h2>
<label for="token">Tenant submission bearer token</label>
<input id="token" type="password" autocomplete="off" placeholder="Only held in this browser tab">
<button id="refresh">Refresh overview</button>
<small>The token is never stored in cookies or browser storage.</small>
</section>
<section>
<h2>Submit validated signal</h2>
<label for="agent">Enrolled agent UUID</label>
<input id="agent" autocomplete="off" placeholder="00000000-0000-0000-0000-000000000000">
<label for="signal">Trading alert</label>
<textarea id="signal" rows="6">BUY XAUUSD CMP 4042.8
SL: 4037
TP-1: 4056
TP-2: 4082</textarea>
<button id="submit">Queue signed demo command</button>
<output id="message" role="status"></output>
</section>
<section>
<h2>Delivery overview</h2>
<p id="counts">Authenticate and refresh to load scoped queue status.</p>
<div style="overflow-x:auto">
<table><thead><tr><th>Command</th><th>Delivery</th><th>Agent report</th></tr></thead>
<tbody id="recent"></tbody></table>
</div>
</section>
<script>
"use strict";
const byId=id=>document.getElementById(id);
async function api(path, options={}) {
  const token=byId("token").value;
  if(!token) throw new Error("Tenant bearer token required");
  const res=await fetch(path,{...options,
    headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"},
    cache:"no-store",redirect:"error"});
  const data=await res.json();
  if(!res.ok) throw new Error("Request rejected ("+res.status+")");
  return data;
}
async function overview() {
  const data=await api("/v1/dev/tenants/overview");
  byId("counts").textContent="Enrolled agents: "+data.agents_enrolled+
    " • "+Object.entries(data.status_counts).map(([k,v])=>k+": "+v).join(" • ");
  byId("recent").replaceChildren();
  for(const item of data.recent) {
    const tr=document.createElement("tr");
    for(const value of [item.command_id,item.status,item.journal_state||"—"]) {
      const cell=document.createElement("td");
      cell.textContent=value;
      tr.appendChild(cell);
    }
    byId("recent").appendChild(tr);
  }
}
byId("refresh").addEventListener("click",async()=>{
  try { await overview(); byId("message").textContent="Overview refreshed"; }
  catch(err) { byId("message").textContent=err.message; }
});
let pendingRequest=null;
byId("submit").addEventListener("click",async()=>{
  const button=byId("submit");button.disabled=true;
  try {
    if(!pendingRequest) pendingRequest={
      request_id:crypto.randomUUID(),requested_at:new Date().toISOString(),
      agent_id:byId("agent").value,text:byId("signal").value};
    const data=await api("/v1/dev/tenants/commands/from-signal",{
      method:"POST",body:JSON.stringify(pendingRequest)});
    pendingRequest=null;
    byId("message").textContent="Queued command: "+data.command_id;
    await overview();
  } catch(err) { byId("message").textContent=err.message; }
  finally { button.disabled=false; }
});
</script>
</body></html>"""


@router.get("/dev/console", response_class=HTMLResponse)
def console():
    return HTMLResponse(PAGE, headers={
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; connect-src 'self'; "
            "form-action 'none'; base-uri 'none'; frame-ancestors 'none'"),
    })
