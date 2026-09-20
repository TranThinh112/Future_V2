import asyncio
import json
import logging

import websockets

log=logging.getLogger(__name__)
async def stream_public(url, args, on_message, stop: asyncio.Event):
    delay=1
    while not stop.is_set():
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                await ws.send(json.dumps({"op":"subscribe","args":args})); delay=1
                async for raw in ws:
                    await on_message(json.loads(raw))
        except (websockets.WebSocketException, OSError, json.JSONDecodeError) as exc:
            log.warning("okx_ws_reconnect", extra={"error":str(exc)}); await asyncio.sleep(delay); delay=min(delay*2,30)

async def stream_private(url, login_message, args, on_message, stop):
    delay=1
    while not stop.is_set():
        try:
            async with websockets.connect(url,ping_interval=20) as ws:
                await ws.send(json.dumps(login_message)); await ws.send(json.dumps({"op":"subscribe","args":args})); delay=1
                async for raw in ws: await on_message(json.loads(raw))
        except (websockets.WebSocketException, OSError, json.JSONDecodeError) as exc:
            log.warning("okx_private_ws_reconnect",extra={"error":type(exc).__name__}); await asyncio.sleep(delay); delay=min(delay*2,30)
