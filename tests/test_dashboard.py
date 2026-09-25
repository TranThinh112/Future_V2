import asyncio
import re
import time
from types import SimpleNamespace

from app.api.main import _group_events, _last_ai_round, audit_backend
from app.execution.paper import PaperBroker
from app.news.service import NewsService
from app.risk.state import RiskState
from app.schemas import AgentDecision, Consensus
from app.storage.repository import summarize


def test_audit_backend_reports_kind_without_credentials():
    postgres = audit_backend("postgresql+asyncpg://crypto:supersecret@127.0.0.1:15432/railway")
    assert postgres == {"kind": "postgres", "target": "127.0.0.1:15432/railway", "durable": True}
    remote = audit_backend("postgresql://postgres:hunter2@containers.railway.app:7000/railway?sslmode=require")
    assert remote["kind"] == "postgres"
    assert remote["target"] == "containers.railway.app:7000/railway"
    for value in (postgres["target"], remote["target"]):
        assert "supersecret" not in value and "hunter2" not in value and "@" not in value
    sqlite = audit_backend("sqlite+aiosqlite:///./crypto.db")
    assert sqlite["kind"] == "sqlite" and sqlite["durable"] is False


def test_dashboard_script_strings_survive_python_escapes():
    from app.api.dashboard import DASHBOARD_HTML

    script = re.search(r"<script>(.*?)</script>", DASHBOARD_HTML, re.DOTALL).group(1)
    assert "\\n\\nThis spends real API tokens" in script
    assert "\n\nThis spends" not in script
    for line in script.splitlines():
        assert line.count("'") % 2 == 0, f"unterminated quote leaked into: {line}"


def test_summarize_aggregates_tokens_and_cost_per_agent():
    rows = [
        {"kind": "consensus", "payload": {"ai_usage": {"agent_count": 8, "input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "estimated_cost_usd": 0.0005}}},
        {"kind": "agent_decision", "payload": {"agent_name": "TIDAL", "input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "estimated_cost_usd": 0.0001, "status": "ok", "veto": False}},
        {"kind": "agent_decision", "payload": {"agent_name": "TIDAL", "input_tokens": 20, "output_tokens": 5, "total_tokens": 25, "estimated_cost_usd": 0.0002, "status": "fallback", "veto": True}},
        {"kind": "paper_tick", "payload": {"symbol": "BTC-USDT"}},
    ]
    summary = summarize(rows)
    assert summary["totals"] == {
        "rounds": 1, "agent_calls": 8, "input_tokens": 100, "output_tokens": 50,
        "total_tokens": 150, "estimated_cost_usd": 0.0005,
    }
    assert len(summary["agents"]) == 1
    tidal = summary["agents"][0]
    assert tidal["agent"] == "TIDAL"
    assert tidal["calls"] == 2
    assert tidal["total_tokens"] == 40
    assert tidal["estimated_cost_usd"] == 0.0003
    assert tidal["fallback_calls"] == 1
    assert tidal["veto_calls"] == 1


def test_group_events_caps_buckets_and_adds_timestamp():
    rows = [{"kind": "paper_tick", "payload": {"symbol": "BTC-USDT"}, "timestamp": 1.5} for _ in range(80)]
    rows.append({"kind": "unknown", "payload": {}, "timestamp": 2.0})
    grouped = _group_events(rows)
    assert len(grouped["paper_tick"]) == 60
    assert grouped["paper_tick"][0]["ts"] == 1.5
    assert grouped["agent_decision"] == [] and grouped["consensus"] == []
    assert "unknown" not in grouped


def test_summarize_tracks_last_24h_window():
    rows = [
        {"kind": "consensus", "timestamp": time.time(), "payload": {"ai_usage": {"agent_count": 8, "input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "estimated_cost_usd": 0.0005}}},
        {"kind": "consensus", "timestamp": time.time() - 200000, "payload": {"ai_usage": {"agent_count": 8, "input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "estimated_cost_usd": 0.0001}}},
    ]
    summary = summarize(rows)
    assert summary["totals"]["rounds"] == 2
    assert summary["last_24h"] == {"rounds": 1, "input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "estimated_cost_usd": 0.0005}


def _vote(agent, action="hold"):
    return {
        "agent_name": agent, "action": action, "confidence": 0.4, "time_horizon": "15m",
        "entry_price": 100.0, "stop_loss_price": 95.0, "take_profit_price": 110.0,
        "suggested_position_pct": 0.05, "reason_codes": ["test"], "invalidators": ["stale"],
        "data_quality": "good", "veto": agent == "RUNE",
    }


def test_last_ai_round_groups_agents_by_round_id():
    consensus = [{
        "ts": 100.0, "symbol": "BTC-USDT", "round_id": "round1", "action": "hold", "score": 0.0,
        "approved": False, "reason_codes": ["invalid_or_veto"], "deterministic_decision": {"action": "buy", "reason": "trend_momentum"},
        "ai_usage": {"agent_count": 8, "input_tokens": 800, "output_tokens": 80, "total_tokens": 880, "estimated_cost_usd": 0.0016, "model": "gpt-5.4-mini"},
        "votes": [_vote("TIDAL"), _vote("RUNE")],
    }]
    decisions = [
        {"ts": 99.0, "symbol": "BTC-USDT", "round_id": "round1", "agent_name": "TIDAL", "input_tokens": 100,
         "output_tokens": 10, "total_tokens": 110, "estimated_cost_usd": 0.0002, "latency_ms": 900.0,
         "status": "ok", "validation_error": "", "response_preview": '{"action":"hold"}'},
        {"ts": 98.9, "symbol": "BTC-USDT", "round_id": "round1", "agent_name": "RUNE", "input_tokens": 100,
         "output_tokens": 10, "total_tokens": 110, "estimated_cost_usd": 0.0002, "latency_ms": 800.0,
         "status": "fallback", "validation_error": "veto", "response_preview": '{"action":"hold","veto":true}'},
        {"ts": 97.0, "symbol": "BTC-USDT", "round_id": "older", "agent_name": "TIDAL", "input_tokens": 1,
         "output_tokens": 1, "total_tokens": 2, "estimated_cost_usd": 9.9, "status": "ok"},
    ]
    round_data = _last_ai_round(consensus, decisions)
    assert round_data["round_id"] == "round1"
    assert round_data["symbol"] == "BTC-USDT"
    assert round_data["consensus"]["action"] == "hold"
    assert round_data["deterministic"] == {"action": "buy", "reason": "trend_momentum"}
    assert [entry["agent"] for entry in round_data["agents"]] == ["TIDAL", "RUNE"]
    tidal, rune = round_data["agents"]
    assert tidal["action"] == "hold" and tidal["estimated_cost_usd"] == 0.0002
    assert tidal["response_preview"] == '{"action":"hold"}'
    assert tidal["invalidators"] == ["stale"]
    assert rune["veto"] is True and rune["status"] == "fallback"
    assert round_data["usage"]["estimated_cost_usd"] == 0.0016
    assert round_data["usage_recorded"] is True
    assert all(entry["usage_recorded"] is True for entry in round_data["agents"])
    assert _last_ai_round([], []) is None


def test_last_ai_round_flags_legacy_rows_without_usage():
    legacy = [{
        "ts": 100.0, "symbol": "ETH-USDT", "action": "hold", "score": 0.0, "approved": False,
        "reason_codes": ["invalid_or_veto"], "votes": [_vote("TIDAL", "buy"), _vote("RUNE")],
    }]
    round_data = _last_ai_round(legacy, [])
    assert round_data["usage_recorded"] is False
    assert round_data["usage"] == {
        "agent_count": 2, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0,
    }
    assert all(entry["usage_recorded"] is False for entry in round_data["agents"])
    assert round_data["agents"][0]["response_preview"] == ""


def test_last_ai_round_falls_back_to_time_window_without_round_id():
    consensus = [{"ts": 100.0, "symbol": "ETH-USDT", "action": "buy", "votes": [_vote("NORO", "buy")], "ai_usage": {}}]
    decisions = [
        {"ts": 99.5, "symbol": "ETH-USDT", "agent_name": "NORO", "input_tokens": 5, "output_tokens": 1,
         "total_tokens": 6, "estimated_cost_usd": 0.0001, "status": "ok"},
        {"ts": 10.0, "symbol": "ETH-USDT", "agent_name": "NORO", "input_tokens": 999, "output_tokens": 999,
         "total_tokens": 1998, "estimated_cost_usd": 9.9, "status": "ok"},
    ]
    round_data = _last_ai_round(consensus, decisions)
    assert round_data["round_id"] is None
    assert len(round_data["agents"]) == 1
    assert round_data["agents"][0]["input_tokens"] == 5
    assert round_data["usage"]["estimated_cost_usd"] == 0.0001


def _candle_rows(count=250):
    rows = []
    for index in range(count):
        price = 100.0 + index
        rows.append([str(1700000000000 + index * 60000), f"{price}", f"{price + 1}", f"{price - 1}", f"{price}", "10", "10", "10", "1"])
    return list(reversed(rows))


class FakeAudit:
    def __init__(self):
        self.rows = []

    async def append(self, kind, payload):
        self.rows.append({"kind": kind, "payload": payload})


class FakeClient:
    async def ticker(self, symbol):
        return {"data": [{"ts": "1700000000000", "bidPx": "99.9", "askPx": "100.1", "last": "100.0", "vol24h": "5", "volCcy24h": "6"}]}

    async def candles(self, symbol, bar="1m", limit=300):
        return {"data": _candle_rows()}

    async def order_book(self, symbol, depth=20):
        return {"data": [{"bids": [["99.9", "1"]], "asks": [["100.1", "1"]]}]}


class FakeOrchestrator:
    def __init__(self):
        self.calls = 0

    async def decision(self, snapshot, on_agent_decision=None):
        votes = []
        for name in ("TIDAL", "NORO", "LUMEN", "ZEPHR", "OKAPI", "RUNE", "VESKA", "MARIN"):
            decision = AgentDecision(agent_name=name, symbol=snapshot["symbol"], action="hold", confidence=0.2, suggested_position_pct=0)
            votes.append(decision)
            self.calls += 1
            if on_agent_decision:
                on_agent_decision({
                    "ts": 1700000000.0 + self.calls, "agent_name": name, "symbol": snapshot["symbol"],
                    "action": "hold", "confidence": 0.2, "time_horizon": "15m", "entry_price": None,
                    "stop_loss_price": None, "take_profit_price": None, "suggested_position_pct": 0,
                    "reason_codes": ["test"], "invalidators": [], "data_quality": "good", "veto": False,
                    "latency_ms": 1.0, "status": "ok", "input_tokens": 100, "output_tokens": 10,
                    "total_tokens": 110, "estimated_cost_usd": 0.0002, "attempts": 1,
                    "validation_error": "", "response_preview": "{}",
                })
        return Consensus(symbol=snapshot["symbol"], action="hold", score=0.0, approved=False, votes=votes, reason_codes=[])


def _probe_worker():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    worker.risk_state = RiskState(worker.broker.cash, worker.broker.cash)
    worker.close_history = {}
    worker.last_ai_advisory_at = {}
    worker.news = NewsService()
    worker.client = FakeClient()
    worker.audit = FakeAudit()
    worker.orchestrator = FakeOrchestrator()
    worker.settings = SimpleNamespace(
        max_position_pct=0.10, position_size_headroom=0.95, risk_per_trade_pct=0.005, max_total_exposure_pct=0.30,
        max_slippage_pct=0.002, max_spread_pct=0.001, enable_paper_execution=False,
        openai_model="gpt-5.4-mini", okx_account_sync=False, ai_precheck_enabled=False,
        okx_api_key="", okx_secret_key="", okx_passphrase="",
    )
    return worker


def test_ai_probe_runs_eight_agents_and_audits_usage():
    worker = _probe_worker()
    result = asyncio.run(worker.ai_probe("BTC-USDT"))
    assert result["symbol"] == "BTC-USDT"
    assert result["price"] == 100.0
    assert len(result["agents"]) == 8
    assert result["ai_usage"]["agent_count"] == 8
    assert result["ai_usage"]["total_tokens"] == 880
    assert round(result["ai_usage"]["estimated_cost_usd"], 10) == 0.0016
    assert result["ai_usage"]["model"] == "gpt-5.4-mini"
    kinds = [row["kind"] for row in worker.audit.rows]
    assert kinds.count("agent_decision") == 8
    assert kinds.count("consensus") == 1
    round_ids = {row["payload"].get("round_id") for row in worker.audit.rows}
    assert len(round_ids) == 1 and None not in round_ids
    consensus_row = next(row["payload"] for row in worker.audit.rows if row["kind"] == "consensus")
    assert consensus_row["deterministic_decision"]["action"] in {"buy", "hold", "sell"}
    assert all("input_context" in row["payload"] for row in worker.audit.rows if row["kind"] == "agent_decision")
    context = next(row["payload"]["input_context"] for row in worker.audit.rows if row["kind"] == "agent_decision")
    assert context["news"]["data_quality"] == "unavailable"
    assert "proposal" in context and "regime" in context and "structure" in context
