import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from xml.etree import ElementTree

import httpx

HIGH_RISK_PATTERN = re.compile(r"hack|exploit|bankrupt|lawsuit|ban|halt|delist|depeg", re.IGNORECASE)
SENTIMENT_SCORES = {"bullish": 1, "bearish": -1, "neutral": 0}


class NewsService:
    """Fetches recent news/sentiment for a symbol from a configurable provider.

    The provider contract is intentionally simple: an HTTP JSON endpoint that
    accepts ``q``/``symbol``/``limit``/``lookback_minutes`` query params and
    returns either a list or ``{"articles"|"news"|"data": [...]}``. Every failure
    path returns an explicit ``unavailable`` payload so callers never crash.
    """

    def __init__(
        self,
        provider_url: str = "",
        api_key: str = "",
        lookback_minutes: int = 180,
        max_items: int = 10,
        cache_seconds: int = 300,
    ):
        self.provider_url = provider_url.strip()
        self.api_key = api_key.strip()
        self.lookback_minutes = lookback_minutes
        self.max_items = max_items
        self.cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def fetch(self, symbol: str) -> dict[str, Any]:
        if not self.provider_url:
            return self.unavailable("news_provider_not_configured", symbol)
        cached = self._cache.get(symbol)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        result = await self._fetch_remote(symbol)
        if result.get("data_quality") == "good" and self.cache_seconds > 0:
            self._cache[symbol] = (time.monotonic() + self.cache_seconds, result)
        return result

    async def _fetch_remote(self, symbol: str) -> dict[str, Any]:
        query = symbol.replace("-USDT", "")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        params = {
            "q": query,
            "symbol": query,
            "limit": str(self.max_items),
            "lookback_minutes": str(self.lookback_minutes),
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3), follow_redirects=True) as client:
                response = await client.get(self.provider_url, params=params, headers=headers)
                response.raise_for_status()
                content_type = getattr(response, "headers", {}).get("content-type", "").lower()
                body = getattr(response, "text", "").lstrip()
                if "xml" in content_type or body.startswith("<"):
                    return self.normalize(self.parse_rss(body, symbol), symbol)
                return self.normalize(response.json(), symbol)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, ElementTree.ParseError):
            return self.unavailable("news_provider_error", symbol)

    @staticmethod
    def parse_rss(xml: str, symbol: str) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(xml)
        query_terms = {symbol.split("-")[0].lower()}
        if symbol == "BTC-USDT":
            query_terms.update({"bitcoin", "btc"})
        elif symbol == "ETH-USDT":
            query_terms.update({"ethereum", "ether", "eth"})
        items = []
        for entry in root.findall(".//item"):
            title = re.sub(r"\s+", " ", unescape(entry.findtext("title", ""))).strip()
            summary = re.sub(r"\s+", " ", unescape(entry.findtext("description", ""))).strip()
            text = f"{title} {summary}".lower()
            if not title and not summary:
                continue
            relevance = 1.0 if any(term in text for term in query_terms) else 0.5
            published = entry.findtext("pubDate", "").strip()
            try:
                published = parsedate_to_datetime(published).astimezone(UTC).isoformat() if published else None
            except (TypeError, ValueError, OverflowError):
                published = published or None
            sentiment = NewsService.infer_sentiment(text)
            items.append({
                "title": title,
                "summary": summary,
                "source": "CoinDesk RSS",
                "published_at": published,
                "url": entry.findtext("link", "").strip(),
                "sentiment": sentiment,
                "relevance": relevance,
            })
        items.sort(key=lambda item: (item["relevance"], item["published_at"] or ""), reverse=True)
        return items

    @staticmethod
    def infer_sentiment(text: str) -> str:
        bullish = ("surge", "rally", "rise", "gain", "inflow", " bullish", "record high", "adoption")
        bearish = ("crash", "drop", "fall", "outflow", "bearish", "hack", "exploit", "ban", "lawsuit")
        bullish_score = sum(text.count(term) for term in bullish)
        bearish_score = sum(text.count(term) for term in bearish)
        if bullish_score > bearish_score:
            return "bullish"
        if bearish_score > bullish_score:
            return "bearish"
        return "neutral"

    @staticmethod
    def unavailable(reason: str, symbol: str = "") -> dict[str, Any]:
        return {
            "symbol": symbol or None,
            "items": [],
            "sentiment_score": None,
            "sentiment_label": "neutral",
            "event_risk": "unknown",
            "freshness_minutes": None,
            "source_count": 0,
            "as_of": None,
            "data_quality": "unavailable",
            "reason": reason,
        }

    def normalize(self, data: Any, symbol: str) -> dict[str, Any]:
        raw_items = data.get("articles", data.get("news", data.get("data", []))) if isinstance(data, dict) else data
        if not isinstance(raw_items, list):
            return self.unavailable("news_response_items_missing", symbol)
        items = []
        for raw in raw_items[: self.max_items]:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title", raw.get("headline", ""))).strip()
            summary = str(raw.get("summary", raw.get("description", ""))).strip()
            if not title and not summary:
                continue
            sentiment = str(raw.get("sentiment", raw.get("sentiment_label", "neutral"))).lower()
            if sentiment not in SENTIMENT_SCORES:
                sentiment = "neutral"
            items.append({
                "title": title[:500],
                "summary": summary[:1000],
                "source": str(raw.get("source", raw.get("source_name", "unknown")))[:200],
                "published_at": raw.get("published_at", raw.get("publishedAt", raw.get("published"))),
                "url": str(raw.get("url", ""))[:1000],
                "sentiment": sentiment,
                "relevance": raw.get("relevance"),
            })
        if not items:
            return self.unavailable("no_recent_news", symbol)
        score = sum(SENTIMENT_SCORES[item["sentiment"]] for item in items) / len(items)
        label = "bullish" if score > 0.25 else "bearish" if score < -0.25 else "neutral"
        published_values = [item["published_at"] for item in items if item["published_at"]]
        return {
            "symbol": symbol,
            "items": items,
            "sentiment_score": round(score, 4),
            "sentiment_label": label,
            "event_risk": "high" if any(HIGH_RISK_PATTERN.search(item["title"]) for item in items) else "normal",
            "freshness_minutes": self._freshness(published_values),
            "source_count": len({item["source"] for item in items}),
            "as_of": datetime.now(UTC).isoformat(timespec="seconds"),
            "data_quality": "good",
        }

    @staticmethod
    def _freshness(values):
        if not values:
            return None
        try:
            parsed = []
            for value in values:
                text = str(value).replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(text)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                parsed.append(timestamp)
            return max(0, int((datetime.now(UTC) - max(parsed)).total_seconds() / 60))
        except (TypeError, ValueError):
            return None
