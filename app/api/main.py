import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

try:
    from prometheus_client import Counter
except ImportError:
    class Counter:  # type: ignore[no-redef]
        def __init__(self,*args,**kwargs): pass
        def inc(self): pass
from app.api.dashboard import DASHBOARD_HTML
from app.api.metrics import install_metrics
from app.config import Settings, TradingMode
from app.monitoring import configure_logging, install_tracing
from app.paper_worker import PaperWorker
from app.storage.repository import repository_from_url

worker: PaperWorker | None = None
worker_task = None
read_repository = None
settings = Settings()
configure_logging()
if settings.trading_mode == TradingMode.live:
    __import__("logging").getLogger("crypto_agent").critical(
        "LIVE TRADING MODE ENABLED - real funds can be affected after operator gate and risk approval"
    )
@asynccontextmanager
async def lifespan(application):
    global worker, worker_task
    if settings.trading_mode.value == "paper":
        worker = PaperWorker(settings)
        worker_task = __import__("asyncio").create_task(worker.run())
    yield
    if worker: worker.stop()
    if worker_task: worker_task.cancel()
    if read_repository:
        await read_repository.close()
app=FastAPI(title="Crypto Agent Bot", version="0.1.0", lifespan=lifespan); requests=Counter("api_requests_total","API requests")
app.add_middleware(GZipMiddleware, minimum_size=1024)
install_metrics(app, lambda: worker)
install_tracing(app, settings)
@app.get("/")
def root():
    requests.inc()
    mode = Settings().trading_mode
    return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Crypto Agent Bot</title><style>
@import url("https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap");
:root{{--ink:#13221e;--cream:#f4f0e5;--mint:#c7e3cb;--orange:#ef7545;--line:#17382e}}*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 85% 8%,#f9b888 0 10%,transparent 29%),linear-gradient(130deg,#d6ead5,#f4f0e5 55%,#c4ddd0);color:var(--ink);font-family:"DM Mono",monospace}}main{{max-width:1060px;margin:auto;padding:9vh 28px}}header{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid var(--line);padding-bottom:28px}}h1{{font:700 clamp(2.6rem,8vw,6.8rem)/.85 Fraunces,serif;letter-spacing:-.075em;margin:0;max-width:680px}}.eyebrow,.label{{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase}}.pill{{background:var(--ink);color:#e8f2e5;border-radius:99px;padding:9px 12px;margin-top:5px}}section{{display:grid;grid-template-columns:1.1fr .9fr;gap:18px;margin-top:24px}}.card{{border:2px solid var(--line);padding:25px;min-height:190px;background:#f8f4ea99}}.status{{background:var(--mint)}}.state{{font:700 3.2rem Fraunces,serif;margin:18px 0 8px}}.paper{{color:#196649}}a{{color:var(--ink);font-weight:500;text-underline-offset:4px}}.notice{{border-left:5px solid var(--orange);padding-left:14px;line-height:1.6}}@media(max-width:650px){{header{{display:block}}section{{grid-template-columns:1fr}}h1{{margin-top:22px}}}}
</style></head><body><main><header><div><p class="eyebrow">OKX Spot / Multi-agent desk</p><h1>Crypto<br>Agent Bot</h1></div><div class="pill">SYSTEM ONLINE</div></header><section><article class="card status"><p class="label">Trading posture</p><div class="state paper">{mode.value.upper()}</div><p>BTC-USDT and ETH-USDT only. The bot fails closed: uncertain data becomes HOLD.</p></article><article class="card"><p class="label">Control room</p><p><a href="/dashboard">Open agent dashboard</a></p><p><a href="/docs">Open API documentation</a></p><p><a href="/health">View machine health</a></p><p class="notice">Live trading remains disabled. No real order can be submitted from this dashboard.</p></article></section></main></body></html>''')
@app.get("/health")
def health():
    requests.inc()
    worker_healthy = bool(worker and worker.healthy())
    return {"status":"ok" if worker_healthy else "degraded","mode":Settings().trading_mode,"paper_worker":worker_healthy,"worker_running":bool(worker and worker.running),"last_tick_at":getattr(worker,"last_tick_at",0),"worker_error":getattr(worker,"last_error","")}
@app.get("/api/events")
async def events(limit: int = 20):
    repository, should_close = acquire_read_repository()
    try:
        return await repository.recent(max(1, min(limit, 100)))
    finally:
        if should_close:
            await repository.close()
@app.get("/api/status")
async def status():
    repository, should_close = acquire_read_repository()
    try:
        recent = await repository.recent(1)
    finally:
        if should_close:
            await repository.close()
    return {"mode":Settings().trading_mode,"worker_running":bool(worker and worker.running),"worker_healthy":bool(worker and worker.healthy()),"last_tick_at":getattr(worker,"last_tick_at",0),"worker_error":getattr(worker,"last_error",""),"last_event":recent[0] if recent else None}
@app.get("/api/consensus")
async def consensus(limit: int = 20):
    repository, should_close = acquire_read_repository()
    try:
        recent = await repository.recent(max(1, min(limit, 100)))
    finally:
        if should_close:
            await repository.close()
    return [row for row in recent if row["kind"] == "consensus"]
@app.get("/api/portfolio")
def portfolio():
    return _portfolio_payload()

def _portfolio_payload():
    if not worker: return {"available":False}
    prices={fill["symbol"]:fill["price"] for fill in worker.broker.fills}
    return {"available":True,"cash":worker.broker.cash,"equity":worker.broker.equity(prices),"positions":[vars(p) for p in worker.broker.positions.values()],"fills":worker.broker.fills[-20:]}

def acquire_read_repository():
    """Reuse one pooled Postgres repository; sqlite keeps a per-request connection."""
    global read_repository
    if settings.database_url.startswith("postgres"):
        if read_repository is None:
            read_repository = repository_from_url(settings.database_url)
        return read_repository, False
    return repository_from_url(settings.database_url), True
@app.post("/api/kill-switch")
def kill_switch():
    if not worker: return {"stopped":False,"reason":"worker_unavailable"}
    worker.stop()
    return {"stopped":True,"mode":"paper","reason":"operator_requested"}
@app.get("/api/config/safety")
def safety_config():
    settings=Settings()
    return {"mode":settings.trading_mode,"live_enabled":settings.enable_live_trading,"allowed_symbols":settings.allowed_symbols,"max_position_pct":settings.max_position_pct,"max_total_exposure_pct":settings.max_total_exposure_pct,"withdrawals_supported":False}

@app.get("/api/runtime")
def runtime():
    """Read-only deployment fingerprint and capability status; never exposes secrets."""
    settings = Settings()
    return {
        "service": "crypto-agent",
        "app_version": "0.1.0",
        "code_revision": os.getenv("RAILWAY_GIT_COMMIT_SHA", os.getenv("GIT_COMMIT_SHA", "unknown")),
        "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID", "unknown"),
        "runtime": {
            "mode": settings.trading_mode,
            "worker_running": bool(worker and worker.running),
            "allowed_symbols": settings.allowed_symbols,
        },
        "capabilities": {
            "audit_backend": audit_backend(settings.database_url)["kind"],
            "ai_advisory": settings.enable_ai_advisory,
            "ai_cost_logging": True,
            "ai_token_logging": True,
            "ai_consensus_cost_totals": True,
            "paper_execution": settings.enable_paper_execution,
            "live_trading": settings.enable_live_trading,
            "withdrawals": False,
        },
    }

EVENT_CAPS={"consensus":30,"agent_decision":120,"paper_tick":60}
AGENT_ORDER=("TIDAL","NORO","LUMEN","ZEPHR","OKAPI","RUNE","VESKA","MARIN")

def audit_backend(database_url: str) -> dict:
    """Describe which audit store the API reads, without ever exposing credentials."""
    url = (database_url or "").strip()
    if url.startswith("postgres"):
        target = url.split("@", 1)[-1].split("?", 1)[0]
        return {"kind": "postgres", "target": target, "durable": True}
    return {"kind": "sqlite", "target": url or "sqlite+aiosqlite:///./crypto.db", "durable": False}

def _last_ai_round(consensus_rows, decision_rows):
    """Rebuild the most recent AI round: verdict, per-agent answers, tokens and cost."""
    if not consensus_rows:
        return None
    latest = consensus_rows[0]
    round_id = latest.get("round_id")
    if round_id:
        candidates = [row for row in decision_rows if row.get("round_id") == round_id]
    else:
        ts = latest.get("ts") or 0
        candidates = [
            row for row in decision_rows
            if row.get("symbol") == latest.get("symbol") and 0 <= ts - (row.get("ts") or 0) <= 180
        ]
    usage_by_agent = {}
    for row in candidates:
        name = row.get("agent_name")
        if name and name not in usage_by_agent:
            usage_by_agent[name] = row
    votes = {vote.get("agent_name"): vote for vote in (latest.get("votes") or [])}
    agents = []
    for name in list(AGENT_ORDER) + sorted(set(votes) - set(AGENT_ORDER)) + sorted(set(usage_by_agent) - set(AGENT_ORDER)):
        if any(entry["agent"] == name for entry in agents):
            continue
        vote = votes.get(name, {})
        usage = usage_by_agent.get(name, {})
        if not vote and not usage:
            continue
        agents.append({
            "agent": name,
            "action": vote.get("action", usage.get("action")),
            "confidence": vote.get("confidence", usage.get("confidence")),
            "time_horizon": vote.get("time_horizon"),
            "entry_price": vote.get("entry_price"),
            "stop_loss_price": vote.get("stop_loss_price"),
            "take_profit_price": vote.get("take_profit_price"),
            "suggested_position_pct": vote.get("suggested_position_pct"),
            "reason_codes": vote.get("reason_codes") or usage.get("reason_codes") or [],
            "invalidators": vote.get("invalidators") or [],
            "data_quality": vote.get("data_quality", usage.get("data_quality")),
            "veto": bool(vote.get("veto", usage.get("veto"))),
            "latency_ms": usage.get("latency_ms"),
            "status": usage.get("status"),
            "validation_error": usage.get("validation_error"),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "estimated_cost_usd": usage.get("estimated_cost_usd", 0.0),
            "response_preview": usage.get("response_preview", ""),
            "usage_recorded": bool(usage),
        })
    usage = dict(latest.get("ai_usage") or {})
    usage_recorded = bool(candidates) or int(usage.get("total_tokens") or 0) > 0
    if not usage:
        usage = {
            "agent_count": len(agents),
            "input_tokens": sum(entry["input_tokens"] for entry in agents),
            "output_tokens": sum(entry["output_tokens"] for entry in agents),
            "total_tokens": sum(entry["total_tokens"] for entry in agents),
            "estimated_cost_usd": round(sum(entry["estimated_cost_usd"] for entry in agents), 10),
        }
    return {
        "round_id": round_id,
        "symbol": latest.get("symbol"),
        "consensus": latest,
        "deterministic": latest.get("deterministic_decision") or {},
        "usage": usage,
        "usage_recorded": usage_recorded,
        "agents": agents,
    }

def _group_events(rows):
    grouped={kind:[] for kind in EVENT_CAPS}
    for row in rows:
        payload=dict(row.get("payload") or {}); payload["ts"]=row.get("timestamp")
        bucket=grouped.get(row.get("kind"))
        if bucket is not None and len(bucket) < EVENT_CAPS[row["kind"]]:
            bucket.append(payload)
    return grouped

@app.get("/dashboard")
def dashboard_page():
    requests.inc()
    return HTMLResponse(DASHBOARD_HTML)

@app.get("/api/dashboard")
async def dashboard_data(limit: int = 300):
    """Read-only aggregate for the operator dashboard: audit tail, AI tokens/cost, portfolio."""
    requests.inc()
    repository, should_close = acquire_read_repository()
    try:
        rows = await repository.recent(max(1, min(limit, 1000)))
        summary = await repository.summary()
    except Exception as exc:  # noqa: BLE001 - surface store outages to the dashboard instead of a 500 traceback
        return JSONResponse(
            {
                "error": f"audit_store_unavailable: {type(exc).__name__}",
                "detail": str(exc)[:200],
                "audit_backend": audit_backend(settings.database_url),
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
            status_code=503,
        )
    finally:
        if should_close:
            await repository.close()
    grouped = _group_events(rows)
    last_prices = {}
    for tick in grouped["paper_tick"]:
        symbol = tick.get("symbol")
        if symbol and symbol not in last_prices and tick.get("price") is not None:
            last_prices[symbol] = {"price": tick["price"], "rsi": tick.get("rsi"), "ts": tick.get("ts")}
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "event_count": len(rows),
        "ai_model": settings.openai_model,
        "runtime": runtime(),
        "health": health(),
        "summary": summary,
        "portfolio": _portfolio_payload(),
        "audit_backend": audit_backend(settings.database_url),
        "last_prices": last_prices,
        "last_ai_round": _last_ai_round(grouped["consensus"], grouped["agent_decision"]),
        "events": grouped,
    }

@app.post("/api/ai/probe")
async def ai_probe(symbol: str = "BTC-USDT"):
    """Operator-triggered single AI round on live data. Spends real OpenAI tokens and audits the result."""
    requests.inc()
    if not worker:
        return JSONResponse({"available": False, "reason": "worker_unavailable"}, status_code=503)
    if symbol not in settings.allowed_symbols:
        return JSONResponse({"available": False, "reason": "unsupported_symbol", "allowed": list(settings.allowed_symbols)}, status_code=400)
    if not settings.openai_api_key:
        return JSONResponse({"available": False, "reason": "openai_key_missing"}, status_code=400)
    return {"available": True, **await worker.ai_probe(symbol)}
