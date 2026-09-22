"""Read-only operator dashboard rendered as a single self-contained page."""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Agent Desk</title>
<style>
:root{--bg:#eef3e8;--panel:#fffaf0;--panel2:#f7f0df;--ink:#10251f;--muted:#6a7871;--line:#17382e;--good:#cfe8cf;--bad:#f7d5c8;--warn:#ffe0b8;--accent:#ef7545;--shadow:0 10px 30px #17382e18}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,#d7ebd5,#f4f0e5 48%,#cddfd4);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;font-size:14px}main{max-width:1480px;margin:0 auto;padding:24px}.mono{font-family:"DM Mono",ui-monospace,SFMono-Regular,Menlo,monospace}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}.eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}.title{font-size:clamp(30px,4vw,52px);line-height:.95;letter-spacing:-.06em;font-weight:900;margin:0}.toolbar{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.pill,button,select{border:1.5px solid var(--line);border-radius:999px;background:#fffaf0cc;padding:8px 12px;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink)}.pill.ok{background:var(--good)}.pill.bad{background:var(--bad)}button{cursor:pointer}button:hover{background:#fff}button:disabled{opacity:.6;cursor:progress}.layout{display:grid;grid-template-columns:1.15fr .85fr;gap:16px}.card{border:2px solid var(--line);background:#fffaf0d9;box-shadow:var(--shadow);padding:16px;border-radius:16px;min-width:0}.card h2{margin:0 0 12px;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}.stack{display:grid;gap:16px}.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.kpi{border:1.5px solid #17382e55;background:var(--panel2);border-radius:14px;padding:13px}.kpi .k{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}.kpi .v{font-size:25px;font-weight:850;margin:5px 0 2px;letter-spacing:-.04em}.kpi .s{font-size:12px;color:var(--muted);line-height:1.35}.hero{display:grid;grid-template-columns:220px 1fr;gap:14px;align-items:stretch}.verdict{border-radius:16px;border:2px solid var(--line);display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:18px;background:var(--panel2)}.verdict .action{font-size:42px;font-weight:900;letter-spacing:-.06em;text-transform:uppercase}.verdict.buy{background:var(--good)}.verdict.sell,.verdict.bad{background:var(--bad)}.verdict.hold{background:#eee8d9}.facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.fact{border:1px solid #17382e33;border-radius:12px;padding:10px;background:#ffffff73}.fact b{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700}.fact span{display:block;margin-top:4px;font-weight:750}.agent-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.agent{border:1.5px solid #17382e55;border-radius:14px;background:#fffdf7;padding:11px}.agent .name{display:flex;justify-content:space-between;gap:8px;font-weight:850}.agent .meta{font-size:12px;color:var(--muted);margin-top:6px;line-height:1.45}.agent.veto{outline:3px solid #b23a2b33}.tag{display:inline-flex;align-items:center;border-radius:999px;border:1px solid var(--line);padding:2px 8px;font-size:11px;text-transform:uppercase;font-weight:800}.tag.buy{background:var(--good)}.tag.sell{background:var(--bad)}.tag.hold{background:#e8e2d3}.tag.bad{background:var(--bad)}.tag.ok{background:var(--good)}.portfolio-head{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px}.pos{border:1.5px solid #17382e55;border-radius:14px;background:#fffdf7;padding:12px;margin-top:10px}.pos-head{display:flex;justify-content:space-between;gap:10px;align-items:center}.pos h3{margin:0;font-size:16px}.pos-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px}.mini{font-size:12px;color:var(--muted)}.mini b{display:block;color:var(--ink);font-size:14px;margin-top:2px}.pnl-pos{color:#19733a}.pnl-neg{color:#b23a2b}.table-wrap{overflow:auto;border-radius:12px;border:1px solid #17382e33}table{width:100%;border-collapse:collapse;font-size:13px;background:#fffdf7}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #17382e22;white-space:nowrap}th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:#f4eddd;position:sticky;top:0}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.muted{color:var(--muted)}.warn{border-left:5px solid var(--accent);background:#ffe6d6;padding:10px 12px;border-radius:10px;margin-top:10px}.details{margin-top:10px}details{font-size:12px;color:var(--muted)}summary{cursor:pointer}pre{white-space:pre-wrap;max-height:280px;overflow:auto;background:#fff;border:1px solid #17382e33;border-radius:10px;padding:10px}.section-title{display:flex;align-items:center;justify-content:space-between;gap:12px}.subgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.empty{color:var(--muted);padding:12px}.footer{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px;color:var(--muted);font-size:12px}
@media(max-width:1200px){.layout,.hero,.subgrid{grid-template-columns:1fr}.kpis,.facts,.portfolio-head{grid-template-columns:repeat(2,1fr)}.agent-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:680px){main{padding:14px}.top{display:block}.toolbar{justify-content:flex-start;margin-top:14px}.kpis,.facts,.portfolio-head,.pos-grid,.agent-grid{grid-template-columns:1fr}.card{padding:12px}}
</style>
</head>
<body>
<main>
  <header class="top">
    <div><p class="eyebrow">OKX read-only / multi-agent desk</p><h1 class="title">AI Agent Desk</h1></div>
    <div class="toolbar">
      <span class="pill" id="p-mode">mode ?</span><span class="pill" id="p-health">worker ?</span><span class="pill" id="p-sync">okx ?</span><span class="pill" id="p-rev">rev ?</span>
      <select id="probe-symbol"><option>BTC-USDT</option><option>ETH-USDT</option></select><button id="probe">Run AI round</button><button id="refresh">Refresh</button>
    </div>
  </header>

  <section class="kpis" id="kpis"></section>

  <div class="layout" style="margin-top:16px">
    <section class="stack">
      <article class="card"><div class="section-title"><h2>Last AI Round</h2><span class="mono muted" id="round-id">-</span></div><div id="last-round"></div></article>
      <article class="card"><div class="section-title"><h2>Agent Votes</h2><span class="muted" id="vote-summary">-</span></div><div id="agent-votes"></div></article>
      <details class="card"><summary><b>More logs</b> · consensus, agent decisions, market scans</summary><div class="details"><h2>Consensus</h2><div id="consensus"></div><h2 style="margin-top:18px">Agent Decisions</h2><div id="decisions"></div><h2 style="margin-top:18px">Market Scans</h2><div id="ticks"></div></div></details>
    </section>
    <aside class="stack">
      <article class="card"><h2>Real OKX Portfolio</h2><div id="portfolio"></div></article>
      <article class="card"><h2>AI Cost By Agent</h2><div id="agent-cost"></div></article>
    </aside>
  </div>
  <div class="footer"><span id="updated">loading...</span><span id="db-info">db ?</span></div>
</main>
<script>
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>\"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
const n = (v, d=2) => (v === null || v === undefined || v === "") ? "-" : Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
const usd = (v) => (v === null || v === undefined || v === "") ? "-" : "$" + Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:4});
const tok = (v) => (v === null || v === undefined) ? "-" : Number(v).toLocaleString();
const pct = (v, d=2) => (v === null || v === undefined || v === "") ? "-" : (Number(v)*100).toFixed(d) + "%";
const when = (ts) => ts ? new Date(Number(ts) < 2000000000 ? Number(ts)*1000 : ts).toLocaleString() : "-";
const clsPnl = (v) => Number(v || 0) >= 0 ? "pnl-pos" : "pnl-neg";
function tag(v){ const x=String(v||"hold").toLowerCase(); return "<span class=\"tag " + esc(x) + "\">" + esc(x) + "</span>"; }
function listPositions(p){ const raw=(p||{}).positions||{}; return Array.isArray(raw) ? raw : Object.values(raw); }
function kpi(k,v,s){ return "<div class=\"kpi\"><div class=\"k\">"+esc(k)+"</div><div class=\"v\">"+v+"</div><div class=\"s\">"+s+"</div></div>"; }
function renderKpis(d){
  const totals=d.summary.totals||{}, day=d.summary.last_24h||{}, p=d.portfolio||{}, lr=d.last_ai_round||{}, u=lr.usage||{};
  const positions=listPositions(p), fallback=(d.summary.agents||[]).reduce((a,x)=>a+Number(x.fallback_calls||0),0), calls=(d.summary.agents||[]).reduce((a,x)=>a+Number(x.calls||0),0);
  $("kpis").innerHTML = [
    kpi("OKX equity", usd(p.equity), "cash " + usd(p.available_cash ?? p.cash) + " · PnL <span class=\"" + clsPnl(p.unrealized_pnl) + "\">" + usd(p.unrealized_pnl) + "</span>"),
    kpi("Open positions", n(positions.length,0), esc(p.source||"paper") + " · read-only"),
    kpi("Last AI cost", lr.usage_recorded ? usd(u.estimated_cost_usd) : "-", tok(u.total_tokens) + " tokens · " + n(u.agent_count,0) + " agents"),
    kpi("24h AI spend", usd(day.estimated_cost_usd), n(day.rounds,0) + " rounds · " + tok(day.total_tokens) + " tokens"),
    kpi("All-time cost", usd(totals.estimated_cost_usd), tok(totals.total_tokens) + " tokens"),
    kpi("AI rounds", n(totals.rounds,0), tok(totals.agent_calls) + " agent calls"),
    kpi("Fallbacks", n(fallback,0), "of " + n(calls,0) + " calls"),
    kpi("Audit DB", (d.audit_backend||{}).kind === "postgres" ? "Postgres" : "SQLite", esc((d.audit_backend||{}).target||"-"))
  ].join("");
}
function renderPortfolio(p){
  if(!p || p.available===false){ $("portfolio").innerHTML="<div class=\"empty\">Worker not available.</div>"; return; }
  const positions=listPositions(p);
  const head="<div class=\"portfolio-head\">"+
    kpi("Equity", usd(p.equity), "account value")+kpi("Cash", usd(p.available_cash ?? p.cash), "available")+
    kpi("Floating PnL", "<span class=\""+clsPnl(p.unrealized_pnl)+"\">"+usd(p.unrealized_pnl)+"</span>", "unrealized")+
    kpi("Margin used", usd(p.margin_used), "read from OKX")+"</div>";
  const rows=positions.length ? positions.map(x=>"<div class=\"pos\"><div class=\"pos-head\"><h3>"+esc(x.symbol)+"</h3>"+tag(x.side)+"</div><div class=\"pos-grid\">"+
    "<div class=\"mini\">Qty<b>"+n(x.quantity,6)+"</b></div><div class=\"mini\">Entry<b>"+n(x.entry_price,6)+"</b></div><div class=\"mini\">Mark<b>"+n(x.mark_price,6)+"</b></div><div class=\"mini\">PnL<b class=\""+clsPnl(x.unrealized_pnl)+"\">"+usd(x.unrealized_pnl)+"</b></div>"+
    "<div class=\"mini\">Margin<b>"+usd(x.margin)+"</b></div><div class=\"mini\">Lev<b>"+n(x.leverage,0)+"x</b></div><div class=\"mini\">Liquidation<b>"+n(x.liquidation_price,6)+"</b></div><div class=\"mini\">Opened<b>"+esc(x.opened_at||"-")+"</b></div>"+
    "</div></div>").join("") : "<div class=\"empty\">No open positions.</div>";
  $("portfolio").innerHTML=head+"<div class=\"muted mono\">synced "+esc(p.synced_at||"-")+" · "+esc(p.source||"-")+"</div>"+rows;
}
function renderLastRound(r, prices){
  if(!r){ $("last-round").innerHTML="<div class=\"empty\">No AI round recorded.</div>"; return; }
  const c=r.consensus||{}, u=r.usage||{}, det=r.deterministic||{}, agents=r.agents||[], buys=agents.filter(a=>a.action==="buy").length, holds=agents.filter(a=>a.action==="hold").length, veto=agents.filter(a=>a.veto).length;
  $("round-id").textContent = (r.round_id||"-") + " · " + (r.symbol||c.symbol||"-");
  const hero="<div class=\"hero\"><div class=\"verdict "+esc(c.action||"hold")+"\"><div class=\"action\">"+esc(c.action||"hold")+"</div><div>approved <b>"+(c.approved?"yes":"no")+"</b></div><div class=\"muted\">score "+n(c.score,3)+"</div></div>"+
    "<div><div class=\"facts\">"+
    "<div class=\"fact\"><b>Cost</b><span>"+(r.usage_recorded?usd(u.estimated_cost_usd):"-")+"</span></div><div class=\"fact\"><b>Tokens</b><span>"+tok(u.total_tokens)+"</span></div><div class=\"fact\"><b>Votes</b><span>"+buys+" buy · "+holds+" hold · "+veto+" veto</span></div>"+
    "<div class=\"fact\"><b>Last call</b><span>"+when(c.ts)+"</span></div><div class=\"fact\"><b>Deterministic</b><span>"+esc(det.action||"-")+"</span></div><div class=\"fact\"><b>Reasons</b><span>"+esc((c.reason_codes||[]).join(", ")||"-")+"</span></div>"+
    "</div></div></div>";
  const warn = c.approved ? "" : "<div class=\"warn\"><b>Not approved.</b> Any veto or degraded data forces HOLD. This dashboard is read-only; no order is sent.</div>";
  $("last-round").innerHTML=hero+warn;
}
function renderAgentVotes(r, prices){
  const agents=(r&&r.agents)||[]; if(!agents.length){ $("agent-votes").innerHTML="<div class=\"empty\">No agent rows.</div>"; return; }
  const buys=agents.filter(a=>a.action==="buy").length, veto=agents.filter(a=>a.veto).length; $("vote-summary").textContent=buys+" buy · "+veto+" veto";
  $("agent-votes").innerHTML="<div class=\"agent-grid\">"+agents.map(a=>{
    const now=prices[a.symbol]?prices[a.symbol].price:null, delta=(now&&a.entry_price)?(now/a.entry_price-1)*100:null;
    return "<div class=\"agent "+(a.veto?"veto":"")+"\"><div class=\"name\"><span>"+esc(a.agent)+"</span>"+tag(a.action)+"</div><div class=\"meta\">conf "+n(a.confidence,2)+" · "+esc(a.data_quality||"-")+(a.veto?" · veto":"")+"<br>entry "+n(a.entry_price)+" · SL "+n(a.stop_loss_price)+" · TP "+n(a.take_profit_price)+"<br>now Δ "+(delta===null?"-":delta.toFixed(3)+"%")+"</div><details><summary>reasons</summary><pre>"+esc((a.reason_codes||[]).join("\n")||"-")+"</pre></details></div>";
  }).join("")+"</div>";
}
function renderAgentCost(agents){
  agents=agents||[]; if(!agents.length){ $("agent-cost").innerHTML="<div class=\"empty\">No AI calls yet.</div>"; return; }
  const max=Math.max(...agents.map(a=>Number(a.estimated_cost_usd||0)),1e-9);
  $("agent-cost").innerHTML="<div class=\"table-wrap\"><table><thead><tr><th>Agent</th><th class=\"num\">Calls</th><th class=\"num\">Cost</th><th class=\"num\">Veto</th><th>Share</th></tr></thead><tbody>"+agents.map(a=>"<tr><td><b>"+esc(a.agent)+"</b></td><td class=\"num\">"+n(a.calls,0)+"</td><td class=\"num\">"+usd(a.estimated_cost_usd)+"</td><td class=\"num\">"+n(a.veto_calls,0)+"</td><td><div class=\"bar\"><i style=\"width:"+Math.round(Number(a.estimated_cost_usd||0)/max*100)+"%\"></i></div></td></tr>").join("")+"</tbody></table></div>";
}
function renderConsensus(rows){ rows=rows||[]; $("consensus").innerHTML=rows.length?"<div class=\"table-wrap\"><table><thead><tr><th>When</th><th>Symbol</th><th>Action</th><th class=\"num\">Score</th><th>Approved</th><th>Reasons</th></tr></thead><tbody>"+rows.slice(0,20).map(r=>"<tr><td>"+when(r.ts)+"</td><td>"+esc(r.symbol)+"</td><td>"+tag(r.action)+"</td><td class=\"num\">"+n(r.score,3)+"</td><td>"+(r.approved?"yes":"no")+"</td><td>"+esc((r.reason_codes||[]).join(", "))+"</td></tr>").join("")+"</tbody></table></div>":"<div class=\"empty\">No consensus rows.</div>"; }
function renderDecisions(rows){ rows=rows||[]; $("decisions").innerHTML=rows.length?"<div class=\"table-wrap\"><table><thead><tr><th>When</th><th>Agent</th><th>Symbol</th><th>Action</th><th>Quality</th><th>Veto</th><th class=\"num\">Entry</th><th class=\"num\">Cost</th></tr></thead><tbody>"+rows.slice(0,80).map(r=>"<tr><td>"+when(r.ts)+"</td><td>"+esc(r.agent_name)+"</td><td>"+esc(r.symbol)+"</td><td>"+tag(r.action)+"</td><td>"+esc(r.data_quality)+"</td><td>"+(r.veto?"yes":"no")+"</td><td class=\"num\">"+n(r.entry_price)+"</td><td class=\"num\">"+usd(r.estimated_cost_usd)+"</td></tr>").join("")+"</tbody></table></div>":"<div class=\"empty\">No decisions.</div>"; }
function renderTicks(rows){ rows=rows||[]; $("ticks").innerHTML=rows.length?"<div class=\"table-wrap\"><table><thead><tr><th>When</th><th>Symbol</th><th class=\"num\">Price</th><th>Action</th><th>Reason</th><th class=\"num\">RSI</th></tr></thead><tbody>"+rows.slice(0,80).map(r=>"<tr><td>"+when(r.ts)+"</td><td>"+esc(r.symbol)+"</td><td class=\"num\">"+n(r.price)+"</td><td>"+tag(r.action)+"</td><td>"+esc(r.reason)+"</td><td class=\"num\">"+n(r.rsi,1)+"</td></tr>").join("")+"</tbody></table></div>":"<div class=\"empty\">No market scans.</div>"; }
async function load(){
  try{
    const res=await fetch("/api/dashboard?limit=200",{cache:"no-store"}); const d=await res.json(); if(d.error){throw new Error(d.error+" "+(d.detail||""));}
    const rt=d.runtime||{}, caps=rt.capabilities||{}, okx=rt.okx_account||{}, backend=d.audit_backend||{};
    $("p-mode").textContent="mode "+((rt.runtime||{}).mode||"?"); $("p-health").textContent=d.health.paper_worker?"worker healthy":"worker degraded"; $("p-health").className="pill "+(d.health.paper_worker?"ok":"bad");
    $("p-sync").textContent=okx.synced?"OKX synced":"OKX not synced"; $("p-sync").className="pill "+(okx.synced?"ok":"bad"); $("p-rev").textContent="rev "+String(rt.code_revision||"unknown").slice(0,8);
    renderKpis(d); renderPortfolio(d.portfolio); renderLastRound(d.last_ai_round,d.last_prices||{}); renderAgentVotes(d.last_ai_round,d.last_prices||{}); renderAgentCost(d.summary.agents); renderConsensus(d.events.consensus); renderDecisions(d.events.agent_decision); renderTicks(d.events.paper_tick);
    $("db-info").textContent="db "+(backend.kind||"?")+" · live="+caps.live_trading+" · paper_exec="+caps.paper_execution+" · read_only="+caps.okx_read_only; $("updated").textContent="updated "+new Date().toLocaleTimeString()+" · last tick "+(d.health.last_tick_at?when(d.health.last_tick_at):"never");
  }catch(error){ $("updated").textContent="dashboard error: "+error; $("last-round").innerHTML="<div class=\"warn\"><b>Dashboard error.</b> "+esc(String(error))+"</div>"; }
}
$("refresh").addEventListener("click",load);
$("probe").addEventListener("click",async()=>{ const symbol=$("probe-symbol").value; if(!confirm("Call all 8 OpenAI agents now for "+symbol+"?\n\nThis spends real API tokens and is written to the audit log.")){return;} $("probe").disabled=true; $("probe").textContent="running..."; try{ const res=await fetch("/api/ai/probe?symbol="+encodeURIComponent(symbol),{method:"POST"}); const d=await res.json(); if(!d.available){alert("AI round unavailable: "+(d.reason||res.status));} else {alert("AI round "+symbol+"\nconsensus="+d.action+" approved="+d.approved+"\ntokens="+tok(d.ai_usage.total_tokens)+" cost="+usd(d.ai_usage.estimated_cost_usd));} await load(); }catch(error){alert("AI round failed: "+error);} finally{$("probe").disabled=false; $("probe").textContent="Run AI round";} });
load(); setInterval(load,10000);
</script>
</body>
</html>
"""
