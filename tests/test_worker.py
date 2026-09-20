from app.config import Settings
from app.paper_worker import PaperWorker


def test_worker_rejects_non_paper():
    try: PaperWorker(Settings(trading_mode="backtest"))
    except ValueError: assert True
    else: assert False


def test_ai_advisory_skips_deterministic_hold():
    worker = PaperWorker(Settings(openai_api_key="key", enable_ai_advisory=True, ai_advisory_on_hold=False))
    should_call, reason = worker.should_call_ai("BTC-USDT", {"action": "hold"}, now=100)
    assert not should_call
    assert reason == "deterministic_hold"


def test_ai_advisory_cooldown_for_non_hold_signal():
    worker = PaperWorker(Settings(openai_api_key="key", enable_ai_advisory=True, ai_advisory_cooldown_seconds=900))
    should_call, reason = worker.should_call_ai("BTC-USDT", {"action": "buy"}, now=1000)
    assert should_call
    assert reason == "ai_advisory_allowed"
    worker.last_ai_advisory_at["BTC-USDT"] = 1000
    should_call, reason = worker.should_call_ai("BTC-USDT", {"action": "buy"}, now=1200)
    assert not should_call
    assert reason == "ai_advisory_cooldown"


def test_ai_advisory_can_be_disabled():
    worker = PaperWorker(Settings(openai_api_key="key", enable_ai_advisory=False))
    should_call, reason = worker.should_call_ai("BTC-USDT", {"action": "buy"}, now=1000)
    assert not should_call
    assert reason == "ai_advisory_disabled"


def test_paper_execution_disabled_by_default():
    settings = Settings()
    assert not settings.enable_paper_execution
