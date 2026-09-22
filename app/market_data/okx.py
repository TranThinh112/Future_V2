import asyncio
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx

REDACTED = "***"

class OKXClient:
    def __init__(self, api_key="", secret_key="", passphrase="", demo=True, base_url="https://www.okx.com", read_only=True):
        self.api_key,self.secret_key,self.passphrase,self.demo=api_key,secret_key,passphrase,demo; self.base_url=base_url
        self.read_only = read_only
    def sign(self, timestamp, method, path, body=""):
        msg=f"{timestamp}{method.upper()}{path}{body}".encode(); return base64.b64encode(hmac.new(self.secret_key.encode(),msg,hashlib.sha256).digest()).decode()
    def private_ws_login_message(self, timestamp=None):
        ts = str(timestamp or int(datetime.now(UTC).timestamp()))
        return {"op":"login","args":[{"apiKey":self.api_key,"passphrase":self.passphrase,"timestamp":ts,"sign":self.sign(ts,"GET","/users/self/verify","")}]}
    def redacted_headers(self, headers):
        return {key: (REDACTED if key.lower() in {"ok-access-key","ok-access-passphrase","ok-access-sign","authorization"} else value) for key, value in headers.items()}
    def validate_symbol(self, symbol):
        if symbol not in ("BTC-USDT", "ETH-USDT"): raise ValueError("unsupported_spot_symbol")
    async def request(self, method, path, *, params=None, body=None, private=False, retries=3):
        body_text=json.dumps(body,separators=(",",":")) if body else ""; last=None
        for attempt in range(retries):
            ts=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00","Z"); headers={"Content-Type":"application/json"}
            if self.demo: headers["x-simulated-trading"]="1"
            if private: headers.update({"OK-ACCESS-KEY":self.api_key,"OK-ACCESS-PASSPHRASE":self.passphrase,"OK-ACCESS-TIMESTAMP":ts,"OK-ACCESS-SIGN":self.sign(ts,method,path,body_text)})
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3)) as c:
                    r=await c.request(method,self.base_url+path,params=params,content=body_text or None,headers=headers)
                    if r.status_code == 429:
                        await asyncio.sleep(min(30, 2**attempt)); continue
                    r.raise_for_status(); return r.json()
            except (httpx.HTTPError, TimeoutError, OSError, ValueError) as e:
                last=e
                if attempt<retries-1: await asyncio.sleep(2**attempt)
        raise last
    async def ticker(self, symbol): self.validate_symbol(symbol); return await self.request("GET","/api/v5/market/ticker",params={"instId":symbol})
    async def candles(self, symbol, bar="1m", limit=300): self.validate_symbol(symbol); return await self.request("GET","/api/v5/market/candles",params={"instId":symbol,"bar":bar,"limit":str(limit)})
    async def order_book(self, symbol, depth=20): self.validate_symbol(symbol); return await self.request("GET","/api/v5/market/books",params={"instId":symbol,"sz":str(depth)})
    async def instruments(self, symbol="SPOT"): return await self.request("GET","/api/v5/public/instruments",params={"instType":symbol})
    async def balances(self): return await self.request("GET","/api/v5/account/balance",private=True)
    async def open_orders(self, symbol=None): return await self.request("GET","/api/v5/trade/orders-pending",params={"instId":symbol} if symbol else None,private=True)
    async def positions(self, symbol=None): return await self.request("GET","/api/v5/account/positions",params={"instId":symbol} if symbol else None,private=True)
    async def create_order(self, body):
        self.validate_symbol(body.get("instId", ""))
        if body.get("tdMode") != "cash": raise ValueError("spot_orders_must_use_cash_mode")
        if self.read_only: raise PermissionError("okx_client_read_only")
        return await self.request("POST","/api/v5/trade/order",body=body,private=True)
    async def cancel_order(self, symbol, order_id):
        if self.read_only: raise PermissionError("okx_client_read_only")
        return await self.request("POST","/api/v5/trade/cancel-order",body={"instId":symbol,"ordId":order_id},private=True)
    async def order_status(self, symbol, order_id): return await self.request("GET","/api/v5/trade/order",params={"instId":symbol,"ordId":order_id},private=True)
    async def trades(self, symbol, limit=100): return await self.request("GET","/api/v5/market/trades",params={"instId":symbol,"limit":str(limit)})
