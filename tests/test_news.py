import asyncio

import httpx

from app.execution.paper import PaperBroker
from app.news.service import NewsService
from app.paper_worker import PaperWorker


def test_news_service_unavailable_without_provider():
    news = asyncio.run(NewsService().fetch("BTC-USDT"))
    assert news["data_quality"] == "unavailable"
    assert news["reason"] == "news_provider_not_configured"
    assert news["items"] == []


def test_news_service_normalizes_articles_and_sentiment(monkeypatch):
    payload = {
        "articles": [
            {
                "title": "Exchange hack drains funds",
                "summary": "A major exploit was reported.",
                "source": "wire",
                "published_at": "2026-09-22T00:00:00Z",
                "sentiment": "Bearish",
                "url": "https://example.test/1",
            },
            {"headline": "ETF inflows continue", "source_name": "desk", "sentiment_label": "bullish"},
            {"title": "", "summary": ""},
        ]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params, headers):
            assert params["symbol"] == "BTC"
            return FakeResponse()

    monkeypatch.setattr("app.news.service.httpx.AsyncClient", FakeClient)
    news = asyncio.run(NewsService("https://news.test/api").fetch("BTC-USDT"))
    assert news["data_quality"] == "good"
    assert news["symbol"] == "BTC-USDT"
    assert news["source_count"] == 2
    assert news["sentiment_label"] == "neutral"
    assert news["event_risk"] == "high"
    assert news["freshness_minutes"] is not None
    assert len(news["items"]) == 2


def test_news_service_provider_error_is_unavailable(monkeypatch):
    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params, headers):
            raise httpx.ConnectError("provider down")

    monkeypatch.setattr("app.news.service.httpx.AsyncClient", FakeClient)
    news = asyncio.run(NewsService("https://news.test/api").fetch("ETH-USDT"))
    assert news["data_quality"] == "unavailable"
    assert news["reason"] == "news_provider_error"


def test_news_service_empty_payload_is_unavailable():
    news = NewsService("https://news.test/api", max_items=5).normalize({"articles": []}, "BTC-USDT")
    assert news["data_quality"] == "unavailable"
    assert news["reason"] == "no_recent_news"


def test_news_service_caches_successful_results(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"title": "Steady market", "sentiment": "neutral"}]

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params, headers):
            calls["count"] += 1
            return FakeResponse()

    monkeypatch.setattr("app.news.service.httpx.AsyncClient", FakeClient)

    async def run():
        service = NewsService("https://news.test/api", cache_seconds=300)
        return await service.fetch("BTC-USDT"), await service.fetch("BTC-USDT")

    first, second = asyncio.run(run())
    assert first["data_quality"] == "good"
    assert second is first
    assert calls["count"] == 1


def test_agent_snapshot_includes_fetched_news():
    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    snapshot = type("Snapshot", (), {"last": 100.0, "bid": 99.9, "ask": 100.1, "timestamp_ms": 1})()
    news = {"items": [{"title": "ETF inflows"}], "data_quality": "good", "sentiment_label": "bullish"}
    result = worker._agent_snapshot(
        "BTC-USDT",
        snapshot,
        {"rsi": 55.0, "ema20": 99.0},
        {"vol24h": 1234.0},
        {"data_quality": "good"},
        0.0002,
        {"data_quality": "good"},
        {"data_quality": "good"},
        news,
        {"action": "hold", "data_quality": "not_applicable"},
        None,
    )
    assert result["news"] is news
    assert result["data_quality"]["news"] == "good"
    assert result["features"] == {"rsi": 55.0, "ema20": 99.0}


def test_worker_fetch_news_returns_unavailable_without_provider():
    worker = object.__new__(PaperWorker)
    worker.news = NewsService()
    news = asyncio.run(worker._fetch_news("BTC-USDT"))
    assert news["data_quality"] == "unavailable"
    assert news["reason"] == "news_provider_not_configured"


def test_worker_fetch_news_never_raises():
    class BrokenNews:
        async def fetch(self, symbol):
            raise RuntimeError("boom")

    worker = object.__new__(PaperWorker)
    worker.news = BrokenNews()
    news = asyncio.run(worker._fetch_news("ETH-USDT"))
    assert news["data_quality"] == "unavailable"
    assert news["reason"] == "news_fetch_exception"
