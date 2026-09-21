"""Read-only operator dashboard rendered as a single self-contained page."""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Agent Desk</title>
<style>
:root{--ink:#13221e;--cream:#f4f0e5;--mint:#c7e3cb;--orange:#ef7545;--line:#17382e;--dim:#5d6f68;--red:#b23a2b}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:linear-gradient(130deg,#d6ead5,#f4f0e5 55%,#c4ddd0);color:var(--ink);font-family:"DM Mono",ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
main{max-width:1400px;margin:auto;padding:28px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:2px solid var(--line);padding-bottom:18px;flex-wrap:wrap}
h1{font-size:clamp(1.8rem,3.4vw,2.9rem);letter-spacing:-.04em;margin:0}
h2{font-size:.78rem;letter-spacing:.14em;text-transform:uppercase;margin:0 0 12px;color:var(--dim)}
.eyebrow{font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin:0 0 6px}
.pills{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.pill{border:1px solid var(--line);border-radius:99px;padding:6px 12px;font-size:.72rem;letter-spacing:.06em;background:#f8f4ea99}
.pill.ok{background:var(--mint)}.pill.bad{background:#f6d3c8}.pill.info{background:var(--ink);color:#e8f2e5}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:18px 0}
.stat{border:2px solid var(--line);background:#f8f4ea;padding:14px 16px}
.stat .k{font-size:.66rem;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.stat .v{font-size:1.55rem;font-weight:700;margin-top:6px;word-break:break-all}
.stat .s{font-size:.7rem;color:var(--dim);margin-top:4px}
.grid{display:grid;grid-template-columns:1.35fr .65fr;gap:14px}
@media(max-width:980px){.grid{grid-template-columns:1fr}}
.card{border:2px solid var(--line);background:#f8f4ea99;padding:16px;margin-bottom:14px;overflow:auto}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #17382e33;white-space:nowrap}
th{font-size:.64rem;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);position:sticky;top:0;background:#f3eee2}
tbody tr:hover{background:#ffffff66}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;border-radius:4px;padding:1px 6px;font-size:.68rem;border:1px solid var(--line)}
.tag.buy{background:var(--mint)}.tag.sell{background:#f6d3c8}.tag.hold{background:#e6e2d6}
.tag.ok{background:var(--mint)}.tag.bad{background:#f6d3c8}
.muted{color:var(--dim)}
.bar{height:6px;background:#17382e22;position:relative;min-width:60px}
.bar i{position:absolute;inset:0 auto 0 0;background:var(--orange)}
details{font-size:11px;color:var(--dim)}
details pre{max-height:260px;overflow:auto;background:#fffdf7;border:1px solid #17382e33;padding:8px;white-space:pre-wrap}
.empty{color:var(--dim);padding:10px 0}
footer{margin-top:18px;color:var(--dim);font-size:.72rem;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
button{font-family:inherit;font-size:.72rem;border:1px solid var(--line);background:#f8f4ea;padding:6px 12px;border-radius:99px;cursor:pointer}
button:disabled{opacity:.55;cursor:progress}
select{font-family:inherit;font-size:.72rem;border:1px solid var(--line);background:#f8f4ea;padding:6px 10px;border-radius:99px}
.note{font-size:.68rem;color:var(--dim);margin-top:8px}
.last{border-width:3px;background:#fdf9ee}
.last-head{border-bottom:1px solid #17382e33;padding-bottom:10px;margin-bottom:12px}
.last-head div{margin-top:2px}
.last-cost{font-size:1.9rem;font-weight:700}
.verdict{margin-bottom:12px;line-height:1.8}
.warn{border-left:5px solid var(--orange);background:#f9e3d8;padding:8px 12px;margin:10px 0;font-size:.75rem;line-height:1.6}
</style>
</head>
<body>
<main>
<header>
<div><p class="eyebrow">OKX Spot / Multi-agent desk</p><h1>AI Agent Desk</h1></div>
<div class="pills">
<span class="pill" id="p-mode">mode ?</span>
<span class="pill" id="p-health">health ?</span>
<span class="pill" id="p-rev">rev ?</span>
<span class="pill" id="p-tick">tick ?</span>
<span class="pill" id="p-db">db ?</span>
<select id="probe-symbol"><option>BTC-USDT</option><option>ETH-USDT</option></select>
<button id="probe" title="Calls all 8 OpenAI agents once on live data">Run AI round</button>
</div>
</header>

<section class="stats" id="stats"></section>

<article class="card last"><h2>Last AI round (agents, tokens, spend)</h2><div id="last-round"></div></article>

<div class="grid">
<article class="card"><h2>AI cost by agent</h2><div id="agent-cost"></div></article>
<article class="card"><h2>Portfolio</h2><div id="portfolio"></div></article>
</div>

<article class="card"><h2>AI consensus rounds</h2><div id="consensus"></div></article>
<article class="card"><h2>Agent decisions (tokens / cost / setup)</h2><div id="decisions"></div></article>
<article class="card"><h2>Market scans</h2><div id="ticks"></div></article>

<footer>
<span id="updated">loading...</span>
<button id="refresh">refresh now</button>
<span class="muted">read-only · auto-refresh 10s · no secrets are ever rendered</span>
</footer>
</main>
<script>
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v === null || v === undefined ? '' : v).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = (v, d = 2) => (v === null || v === undefined || v === '') ? '-' : Number(v).toLocaleString(undefined, {maximumFractionDigits: d});
const tok = (v) => (v === null || v === undefined) ? '-' : Number(v).toLocaleString();
const usd = (v) => {
  if (v === null || v === undefined) return '-';
  const n = Number(v);
  if (n === 0) return '$0';
  if (Math.abs(n) < 0.000001) return '<$0.000001';
  if (Math.abs(n) < 0.01) return '$' + n.toFixed(6);
  return '$' + n.toFixed(4);
};
const when = (ts) => {
  if (!ts) return '-';
  const ms = ts > 1e12 ? ts : ts * 1000;
  const d = new Date(ms);
  const age = Math.round((Date.now() - ms) / 1000);
  return d.toLocaleTimeString() + ' (' + (age < 60 ? age + 's' : age < 3600 ? Math.round(age / 60) + 'm' : Math.round(age / 3600) + 'h') + ' ago)';
};
const tag = (v) => '<span class="tag ' + esc(v) + '">' + esc(v) + '</span>';

function renderStats(d) {
  const t = d.summary.totals, p = d.portfolio || {};
  const fallback = d.summary.agents.reduce((a, x) => a + x.fallback_calls, 0);
  const calls = d.summary.agents.reduce((a, x) => a + x.calls, 0);
  const day = d.summary.last_24h || {};
  const lr = d.last_ai_round || {};
  const lrUsage = lr.usage || {};
  const items = [
    ['AI rounds', num(t.rounds, 0), num(t.agent_calls, 0) + ' agent calls logged'],
    ['Total tokens', tok(t.total_tokens), 'in ' + tok(t.input_tokens) + ' / out ' + tok(t.output_tokens)],
    ['Total AI cost (all time)', usd(t.estimated_cost_usd), 'model ' + esc(d.ai_model || '-')],
    ['AI cost (24h)', usd(day.estimated_cost_usd), num(day.rounds, 0) + ' rounds · ' + tok(day.total_tokens) + ' tokens'],
    ['Last round cost', lr.usage_recorded ? usd(lrUsage.estimated_cost_usd) : '<span class="muted">not recorded</span>', lr.round_id ? 'round ' + esc(lr.round_id) : (lr.symbol ? 'legacy round ' + esc(lr.symbol) : 'no round recorded yet')],
    ['Agent fallbacks', num(fallback, 0), 'of ' + num(calls, 0) + ' agent calls'],
    ['Paper equity', usd(p.equity), 'cash ' + usd(p.cash)],
    ['Open positions', num((p.positions || []).length, 0), 'fills ' + num((p.fills || []).length, 0)],
    ['Audit database', (d.audit_backend || {}).kind === 'postgres' ? 'PostgreSQL' : 'SQLite', esc((d.audit_backend || {}).target || '-') + ' · ' + ((d.audit_backend || {}).durable ? 'durable' : 'ephemeral (local only)')],
  ];
  $('stats').innerHTML = items.map(([k, v, s]) => '<div class="stat"><div class="k">' + k + '</div><div class="v">' + v + '</div><div class="s">' + s + '</div></div>').join('');
}

function renderLastRound(r, prices) {
  if (!r) { $('last-round').innerHTML = '<div class="empty">No AI round recorded yet. Use "Run AI round" to call all 8 agents on live data.</div>'; return; }
  const u = r.usage || {}, c = r.consensus || {}, det = r.deterministic || {};
  const recorded = r.usage_recorded === true;
  const head =
    '<div class="last-head">' +
      '<div class="last-cost">' + (recorded ? usd(u.estimated_cost_usd) : '<span class="muted">spend not recorded</span>') + '</div>' +
      '<div>' + (recorded ? (num(u.agent_count, 0) + ' agents · ' + tok(u.total_tokens) + ' tokens (in ' + tok(u.input_tokens) + ' / out ' + tok(u.output_tokens) + ')') : '<span class="muted">this round has no token/cost data stored</span>') + '</div>' +
      '<div class="muted">last call: ' + when(c.ts) + ' · ' + esc(r.symbol || c.symbol || '-') + (r.round_id ? ' · round ' + esc(r.round_id) : ' · legacy round (no round_id)') + ' · model ' + esc(u.model || '-') + '</div>' +
    '</div>';
  const notice = recorded ? '' :
    '<div class="warn"><b>Why 0?</b> This is the newest AI round in the audit log, but it was written by an older build that did not store tokens, cost, latency or raw model output per agent, so there is nothing to sum. This does not mean the call was free. Press <b>Run AI round</b> to run one round with the current build and capture every field.</div>';
  const detText = det.action ? ('deterministic trigger: ' + det.action + ' (' + (det.reason || '-') + ')' +
      (det.stop_loss ? ' · SL ' + num(det.stop_loss) + ' · TP ' + num(det.take_profit) : '')) : 'deterministic trigger: -';
  const verdict =
    '<div class="verdict">' + tag(c.action || 'hold') + ' consensus score <b>' + num(c.score, 3) + '</b> · approved <b>' + (c.approved ? 'yes' : 'no') + '</b>' +
    ' · reason codes: ' + esc((c.reason_codes || []).join(', ') || '-') +
    '<div class="muted">' + detText + '</div></div>';
  const rows = (r.agents || []).map(a => {
    const now = prices[a.symbol] ? prices[a.symbol].price : null;
    const delta = (now && a.entry_price) ? (now / a.entry_price - 1) * 100 : null;
    const has = a.usage_recorded === true;
    const cost = has ? usd(a.estimated_cost_usd) : '<span class="muted" title="this round stored no cost">n/a</span>';
    const latency = has ? num(a.latency_ms, 0) : '<span class="muted">n/a</span>';
    const status = has ? esc(a.status || '-') : '<span class="muted">not recorded</span>';
    const says = a.response_preview
      ? '<details><summary>' + esc(a.action || '-') + ' · ' + esc((a.reason_codes || []).join(',')) + '</summary><pre>' + esc(a.response_preview) + '</pre>' + (a.invalidators && a.invalidators.length ? '<div class="muted">invalidators: ' + esc(a.invalidators.join(', ')) + '</div>' : '') + '</details>'
      : '<span class="muted">no raw output stored · reason codes: ' + esc((a.reason_codes || []).join(',')) + '</span>';
    const tokensIn = has ? tok(a.input_tokens) : '<span class="muted">n/a</span>';
    const tokensOut = has ? tok(a.output_tokens) : '<span class="muted">n/a</span>';
    return '<tr><td><b>' + esc(a.agent) + '</b></td><td>' + tag(a.action || 'hold') + '</td><td class="num">' + num(a.confidence, 2) + '</td><td>' + esc(a.time_horizon || '-') + '</td><td class="num">' + num(a.entry_price) + '</td><td class="num">' + num(a.stop_loss_price) + '</td><td class="num">' + num(a.take_profit_price) + '</td><td class="num">' + (a.suggested_position_pct === null || a.suggested_position_pct === undefined ? '-' : (100 * Number(a.suggested_position_pct)).toFixed(2) + '%') + '</td><td>' + esc(a.data_quality || '-') + '</td><td>' + (a.veto ? '<span class="tag bad">veto</span>' : 'no') + '</td><td class="num">' + tokensIn + '</td><td class="num">' + tokensOut + '</td><td class="num">' + cost + '</td><td class="num">' + latency + '</td><td>' + status + (a.validation_error ? ' <span class="muted" title="' + esc(a.validation_error) + '">!</span>' : '') + '</td><td>' + says + '</td><td class="num">' + (delta === null ? '-' : delta.toFixed(3) + '%') + '</td></tr>';
  }).join('');
  $('last-round').innerHTML = head + notice + verdict +
    '<table><thead><tr><th>Agent</th><th>Action</th><th class="num">Conf</th><th>Horizon</th><th class="num">Entry</th><th class="num">SL</th><th class="num">TP</th><th class="num">Pos %</th><th>Quality</th><th>Veto</th><th class="num">In tokens</th><th class="num">Out tokens</th><th class="num">Cost USD</th><th class="num">Latency ms</th><th>Status</th><th>Agent returned</th><th class="num">Entry vs now</th></tr></thead><tbody>' + (rows || '<tr><td colspan="17" class="muted">no agent rows in this round</td></tr>') + '</tbody></table>';
}

function renderAgentCost(agents) {
  if (!agents.length) { $('agent-cost').innerHTML = '<div class="empty">No AI agent calls recorded yet.</div>'; return; }
  const max = Math.max(...agents.map(a => a.estimated_cost_usd)) || 1;
  $('agent-cost').innerHTML = '<table><thead><tr><th>Agent</th><th class="num">Calls</th><th class="num">In</th><th class="num">Out</th><th class="num">Total</th><th class="num">Cost USD</th><th class="num">Fallback</th><th class="num">Veto</th><th>Share</th></tr></thead><tbody>' +
    agents.map(a => '<tr><td>' + esc(a.agent) + '</td><td class="num">' + num(a.calls, 0) + '</td><td class="num">' + tok(a.input_tokens) + '</td><td class="num">' + tok(a.output_tokens) + '</td><td class="num">' + tok(a.total_tokens) + '</td><td class="num" title="' + a.estimated_cost_usd + '">' + usd(a.estimated_cost_usd) + '</td><td class="num">' + num(a.fallback_calls, 0) + '</td><td class="num">' + num(a.veto_calls, 0) + '</td><td><div class="bar"><i style="width:' + Math.max(2, Math.round(100 * a.estimated_cost_usd / max)) + '%"></i></div></td></tr>').join('') +
    '</tbody></table>';
}

function renderPortfolio(p) {
  if (!p || p.available === false) { $('portfolio').innerHTML = '<div class="empty">Worker not running in this process.</div>'; return; }
  const rows = (p.positions || []).map(x => '<tr><td>' + esc(x.symbol) + '</td><td class="num">' + num(x.quantity, 6) + '</td><td class="num">' + num(x.entry_price) + '</td><td class="num">' + num(x.stop_loss) + '</td><td class="num">' + num(x.take_profit) + '</td><td class="num">' + (x.opened_at ? when(x.opened_at) : '-') + '</td></tr>').join('');
  $('portfolio').innerHTML =
    '<div class="muted">cash ' + usd(p.cash) + ' · equity ' + usd(p.equity) + ' · positions ' + (p.positions || []).length + '</div>' +
    '<table><thead><tr><th>Symbol</th><th class="num">Qty</th><th class="num">Entry</th><th class="num">Stop</th><th class="num">Target</th><th>Opened</th></tr></thead><tbody>' + (rows || '<tr><td colspan="6" class="muted">flat</td></tr>') + '</tbody></table>';
}

function renderConsensus(rows) {
  if (!rows.length) { $('consensus').innerHTML = '<div class="empty">No consensus rounds recorded yet.</div>'; return; }
  $('consensus').innerHTML = '<table><thead><tr><th>When</th><th>Symbol</th><th>Action</th><th class="num">Score</th><th>Approved</th><th class="num">Agents</th><th class="num">Tokens</th><th class="num">Cost USD</th><th>Reason codes</th><th>Model</th></tr></thead><tbody>' +
    rows.map(r => {
      const u = r.ai_usage || {};
      return '<tr><td>' + when(r.ts) + '</td><td>' + esc(r.symbol) + '</td><td>' + tag(r.action) + '</td><td class="num">' + num(r.score, 3) + '</td><td>' + (r.approved ? tag('ok') : tag('bad')) + '</td><td class="num">' + num(u.agent_count, 0) + '</td><td class="num">' + tok(u.total_tokens) + '</td><td class="num" title="' + u.estimated_cost_usd + '">' + usd(u.estimated_cost_usd) + '</td><td>' + esc((r.reason_codes || []).join(', ')) + '</td><td class="muted">' + esc(u.model || '-') + '</td></tr>';
    }).join('') + '</tbody></table>';
}

function renderDecisions(rows, prices) {
  if (!rows.length) { $('decisions').innerHTML = '<div class="empty">No agent decisions recorded yet.</div>'; return; }
  $('decisions').innerHTML = '<table><thead><tr><th>When</th><th>Agent</th><th>Symbol</th><th>Action</th><th class="num">Conf</th><th>Horizon</th><th>Quality</th><th>Veto</th><th class="num">Entry</th><th class="num">SL</th><th class="num">TP</th><th class="num">Now</th><th class="num">vs Entry</th><th class="num">In</th><th class="num">Out</th><th class="num">Cost USD</th><th class="num">Latency ms</th><th>Status</th><th>Context</th></tr></thead><tbody>' +
    rows.map(r => {
      const now = prices[r.symbol] ? prices[r.symbol].price : null;
      const delta = (now && r.entry_price) ? (now / r.entry_price - 1) * 100 : null;
      const cls = delta === null ? '' : (delta >= 0 ? 'tag buy' : 'tag sell');
      const ctx = r.input_context ? '<details><summary>view</summary><pre>' + esc(JSON.stringify(r.input_context, null, 1)) + '</pre></details>' : '<span class="muted">-</span>';
      return '<tr><td>' + when(r.ts) + '</td><td>' + esc(r.agent_name) + '</td><td>' + esc(r.symbol) + '</td><td>' + tag(r.action) + '</td><td class="num">' + num(r.confidence, 2) + '</td><td>' + esc(r.time_horizon) + '</td><td>' + esc(r.data_quality) + '</td><td>' + (r.veto ? 'yes' : 'no') + '</td><td class="num">' + num(r.entry_price) + '</td><td class="num">' + num(r.stop_loss_price) + '</td><td class="num">' + num(r.take_profit_price) + '</td><td class="num">' + num(now) + '</td><td class="num"><span class="' + cls + '">' + (delta === null ? '-' : delta.toFixed(3) + '%') + '</span></td><td class="num">' + tok(r.input_tokens) + '</td><td class="num">' + tok(r.output_tokens) + '</td><td class="num" title="' + r.estimated_cost_usd + '">' + usd(r.estimated_cost_usd) + '</td><td class="num">' + num(r.latency_ms, 0) + '</td><td>' + esc(r.status || '') + (r.validation_error ? ' <span class="muted" title="' + esc(r.validation_error) + '">!</span>' : '') + '</td><td>' + ctx + '</td></tr>';
    }).join('') + '</tbody></table>';
}

function renderTicks(rows) {
  if (!rows.length) { $('ticks').innerHTML = '<div class="empty">No market scans recorded yet.</div>'; return; }
  $('ticks').innerHTML = '<table><thead><tr><th>When</th><th>Symbol</th><th class="num">Price</th><th>Action</th><th>Reason</th><th class="num">Spread</th><th class="num">RSI</th><th class="num">EMA20</th><th>Consensus</th><th>Persisted</th></tr></thead><tbody>' +
    rows.map(r => {
      const c = r.agent_consensus || {};
      return '<tr><td>' + when(r.ts) + '</td><td>' + esc(r.symbol) + '</td><td class="num">' + num(r.price) + '</td><td>' + tag(r.action) + '</td><td>' + esc(r.reason) + '</td><td class="num">' + (r.spread_pct === undefined ? '-' : Number(r.spread_pct).toFixed(6)) + '</td><td class="num">' + num(r.rsi) + '</td><td class="num">' + num(r.ema20) + '</td><td>' + esc(c.action || '-') + (c.approved ? ' ' + tag('ok') : '') + (c.skipped ? ' <span class="muted">skipped:' + esc((c.reason_codes || []).join(',')) + '</span>' : '') + '</td><td>' + (r.audit_persisted ? 'yes' : 'no') + '</td></tr>';
    }).join('') + '</tbody></table>';
}

async function load() {
  try {
    const res = await fetch('/api/dashboard?limit=200', {cache: 'no-store'});
    const d = await res.json();
    if (d.error) { throw new Error(d.error + ' (' + ((d.audit_backend || {}).target || 'unknown') + ') ' + (d.detail || '')); }
    const rt = d.runtime || {};
    $('p-mode').textContent = 'mode ' + ((rt.runtime || {}).mode || rt.mode || '?');
    $('p-health').textContent = d.health.paper_worker ? 'worker healthy' : 'worker degraded';
    $('p-health').className = 'pill ' + (d.health.paper_worker ? 'ok' : 'bad');
    $('p-rev').textContent = 'rev ' + String(d.runtime.code_revision || 'unknown').slice(0, 8);
    $('p-tick').textContent = 'last tick ' + (d.health.last_tick_at ? when(d.health.last_tick_at) : 'never');
    const backend = d.audit_backend || {};
    $('p-db').textContent = 'db ' + (backend.kind || '?') + (backend.kind === 'sqlite' ? ' (local, not production)' : '');
    $('p-db').className = 'pill ' + (backend.kind === 'postgres' ? 'ok' : 'bad');
    renderStats(d);
    renderLastRound(d.last_ai_round, d.last_prices || {});
    renderAgentCost(d.summary.agents);
    renderPortfolio(d.portfolio);
    renderConsensus(d.events.consensus);
    renderDecisions(d.events.agent_decision, d.last_prices || {});
    renderTicks(d.events.paper_tick);
    $('updated').textContent = 'updated ' + new Date().toLocaleTimeString() + ' · ' + num(d.event_count, 0) + ' audit rows scanned';
  } catch (error) {
    $('updated').textContent = 'dashboard error: ' + error;
    $('last-round').innerHTML = '<div class="warn"><b>Audit store unreachable.</b> ' + esc(String(error)) + '</div>';
  }
}
$('refresh').addEventListener('click', load);
$('probe').addEventListener('click', async () => {
  const symbol = $('probe-symbol').value;
  if (!confirm('Call all 8 OpenAI agents now for ' + symbol + '?\n\nThis spends real API tokens and is written to the audit log.')) return;
  $('probe').disabled = true; $('probe').textContent = 'running...';
  try {
    const res = await fetch('/api/ai/probe?symbol=' + encodeURIComponent(symbol), {method: 'POST'});
    const d = await res.json();
    if (!d.available) { alert('AI round unavailable: ' + (d.reason || res.status)); }
    else {
      alert('AI round ' + symbol + '\nprice=' + num(d.price) + '  deterministic=' + (d.deterministic || {}).action +
        '\nconsensus=' + d.action + '  score=' + num(d.score, 3) + '  approved=' + d.approved +
        '\nagents=' + d.ai_usage.agent_count + '  tokens=' + tok(d.ai_usage.total_tokens) + '  cost=' + usd(d.ai_usage.estimated_cost_usd));
    }
    await load();
  } catch (error) { alert('AI round failed: ' + error); }
  finally { $('probe').disabled = false; $('probe').textContent = 'Run AI round'; }
});
load();
setInterval(load, 10000);
</script>
</body>
</html>
"""
