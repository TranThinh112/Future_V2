import asyncio
import json
import logging

import httpx
from pydantic import ValidationError

from app.schemas import AgentDecision

from .base import hold
from .prompts import PROMPTS, SYSTEM_SUFFIX

log = logging.getLogger("crypto_agent.agents")
SECRET_KEYWORDS = ("key", "secret", "passphrase", "password", "token", "authorization")

def sanitize_snapshot(value):
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if any(word in str(key).lower() for word in SECRET_KEYWORDS):
                continue
            clean[key] = sanitize_snapshot(item)
        return clean
    if isinstance(value, list):
        return [sanitize_snapshot(item) for item in value]
    return value

def _response_text(data):
    if data.get("output_text"):
        return data["output_text"]
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in (None, "output_text") and content.get("text"):
                return content["text"]
    return ""

def _normalize_decision(raw_text, agent_name, snapshot):
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise TypeError("agent_output_must_be_object")
    action = str(payload.get("action", "hold")).lower()
    if action not in {"buy", "sell", "hold", "reduce", "emergency_exit"}:
        action = "hold"
    reason_codes = payload.get("reason_codes", ["model_output"])
    invalidators = payload.get("invalidators", [])
    if isinstance(reason_codes, str):
        reason_codes = [reason_codes]
    if isinstance(invalidators, str):
        invalidators = [invalidators]
    payload.update({
        "agent_name": agent_name,
        "symbol": snapshot.get("symbol", ""),
        "action": action,
        "time_horizon": payload.get("time_horizon", "15m"),
        "entry_price": payload.get("entry_price"),
        "stop_loss_price": payload.get("stop_loss_price"),
        "take_profit_price": payload.get("take_profit_price"),
        "suggested_position_pct": payload.get("suggested_position_pct", 0),
        "reason_codes": reason_codes,
        "invalidators": invalidators,
        "data_quality": payload.get("data_quality", snapshot.get("data_quality", "degraded")),
        "veto": payload.get("veto", False),
    })
    return AgentDecision.model_validate(payload)

class OpenAIAgent:
    def __init__(self, name, api_key, model="gpt-5.4-mini", timeout=20, retries=2):
        self.name=name; self.key=api_key; self.model=model; self.timeout=timeout; self.retries=retries
    async def decide(self, snapshot):
        if not self.key: return hold(self.name,snapshot.get("symbol",""),"openai_key_missing")
        safe_snapshot = sanitize_snapshot(snapshot)
        payload={"model":self.model,"input":[{"role":"system","content":PROMPTS[self.name]+SYSTEM_SUFFIX},{"role":"user","content":json.dumps(safe_snapshot,separators=(",",":"))}],"text":{"format":{"type":"json_object"}},"store":False}
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    r=await c.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {self.key}"},json=payload); r.raise_for_status(); data=r.json()
                usage = data.get("usage", {})
                if usage:
                    log.info("openai_usage", extra={"agent": self.name, "model": self.model, "usage": usage})
                text = _response_text(data)
                return _normalize_decision(text, self.name, snapshot)
            except (httpx.HTTPError, TimeoutError, ValueError, KeyError, IndexError, ValidationError) as exc:
                last_error = exc
                if attempt < self.retries:
                    await asyncio.sleep(min(4, 2**attempt))
        log.warning("openai_agent_hold", extra={"agent": self.name, "error": str(last_error)})
        return hold(self.name,snapshot.get("symbol",""),"malformed_or_timeout")
