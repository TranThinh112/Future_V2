import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

try:
    from prometheus_client import Counter
except ImportError:
    class Counter:  # type: ignore[no-redef]
        def __init__(self,*args,**kwargs): pass
        def inc(self): pass
from app.api.metrics import install_metrics
from app.config import Settings, TradingMode
from app.monitoring import configure_logging, install_tracing
from app.paper_worker import PaperWorker
from app.storage.repository import AuditRepository

worker: PaperWorker | None = None
worker_task = None
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
app=FastAPI(title="Crypto Agent Bot", version="0.1.0", lifespan=lifespan); requests=Counter("api_requests_total","API requests")
install_metrics(app, lambda: worker)
install_tracing(app, settings)
@app.get("/")
def root():
    requests.inc()
    mode = Settings().trading_mode
    return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Crypto Agent Bot</title><style>
@import url("https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap");
:root{{--ink:#13221e;--cream:#f4f0e5;--mint:#c7e3cb;--orange:#ef7545;--line:#17382e}}*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 85% 8%,#f9b888 0 10%,transparent 29%),linear-gradient(130deg,#d6ead5,#f4f0e5 55%,#c4ddd0);color:var(--ink);font-family:"DM Mono",monospace}}main{{max-width:1060px;margin:auto;padding:9vh 28px}}header{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid var(--line);padding-bottom:28px}}h1{{font:700 clamp(2.6rem,8vw,6.8rem)/.85 Fraunces,serif;letter-spacing:-.075em;margin:0;max-width:680px}}.eyebrow,.label{{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase}}.pill{{background:var(--ink);color:#e8f2e5;border-radius:99px;padding:9px 12px;margin-top:5px}}section{{display:grid;grid-template-columns:1.1fr .9fr;gap:18px;margin-top:24px}}.card{{border:2px solid var(--line);padding:25px;min-height:190px;background:#f8f4ea99}}.status{{background:var(--mint)}}.state{{font:700 3.2rem Fraunces,serif;margin:18px 0 8px}}.paper{{color:#196649}}a{{color:var(--ink);font-weight:500;text-underline-offset:4px}}.notice{{border-left:5px solid var(--orange);padding-left:14px;line-height:1.6}}@media(max-width:650px){{header{{display:block}}section{{grid-template-columns:1fr}}h1{{margin-top:22px}}}}
</style></head><body><main><header><div><p class="eyebrow">OKX Spot / Multi-agent desk</p><h1>Crypto<br>Agent Bot</h1></div><div class="pill">SYSTEM ONLINE</div></header><section><article class="card status"><p class="label">Trading posture</p><div class="state paper">{mode.value.upper()}</div><p>BTC-USDT and ETH-USDT only. The bot fails closed: uncertain data becomes HOLD.</p></article><article class="card"><p class="label">Control room</p><p><a href="/docs">Open API documentation</a></p><p><a href="/health">View machine health</a></p><p class="notice">Live trading remains disabled. No real order can be submitted from this dashboard.</p></article></section></main></body></html>''')
@app.get("/health")
def health(): requests.inc(); return {"status":"ok","mode":Settings().trading_mode,"paper_worker":bool(worker and worker.running)}
@app.get("/api/events")
def events(limit: int = 20):
    return AuditRepository().recent(max(1, min(limit, 100)))
@app.get("/api/status")
def status():
    recent = AuditRepository().recent(1)
    return {"mode":Settings().trading_mode,"worker_running":bool(worker and worker.running),"last_event":recent[0] if recent else None}
@app.get("/api/consensus")
def consensus(limit: int = 20):
    return [row for row in AuditRepository().recent(max(1, min(limit,100))) if row["kind"] == "consensus"]
@app.get("/api/portfolio")
def portfolio():
    if not worker: return {"available":False}
    prices={fill["symbol"]:fill["price"] for fill in worker.broker.fills}
    return {"available":True,"cash":worker.broker.cash,"equity":worker.broker.equity(prices),"positions":[vars(p) for p in worker.broker.positions.values()],"fills":worker.broker.fills[-20:]}
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
            "ai_advisory": settings.enable_ai_advisory,
            "ai_cost_logging": True,
            "ai_token_logging": True,
            "ai_consensus_cost_totals": True,
            "paper_execution": settings.enable_paper_execution,
            "live_trading": settings.enable_live_trading,
            "withdrawals": False,
        },
    }
