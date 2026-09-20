import asyncio

import pytest

from app.market_data import ws as ws_module


def test_public_ws_reconnects_after_failure(monkeypatch):
    calls = {"connect": 0, "messages": 0}

    class FailingConnection:
        async def __aenter__(self):
            calls["connect"] += 1
            raise ConnectionError("temporary")
        async def __aexit__(self, exc_type, exc, tb):
            return None

    class WorkingConnection:
        async def __aenter__(self):
            calls["connect"] += 1
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return None
        async def send(self, payload):
            return None
        def __aiter__(self):
            return self
        async def __anext__(self):
            calls["messages"] += 1
            if calls["messages"] == 1:
                return '{"event":"subscribe"}'
            raise asyncio.CancelledError()

    def fake_connect(*args, **kwargs):
        return FailingConnection() if calls["connect"] == 0 else WorkingConnection()

    async def fast_sleep(delay):
        return None

    received = []
    stop = asyncio.Event()

    async def on_message(message):
        received.append(message)
        stop.set()
        raise asyncio.CancelledError()

    monkeypatch.setattr(ws_module.websockets, "connect", fake_connect)
    monkeypatch.setattr(ws_module.asyncio, "sleep", fast_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ws_module.stream_public("wss://example", [], on_message, stop))

    assert calls["connect"] == 2
    assert received == [{"event": "subscribe"}]
