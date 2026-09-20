import asyncio
import json
import logging
import math

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

def _number(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _optional_number(value):
    if value is None or value == "":
        return None
    number = _number(value, float("nan"))
    return number if math.isfinite(number) else None


def _normalize_decision(raw_text, agent_name, snapshot):
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise TypeError("agent_output_must_be_object")
    action = str(payload.get("action", "hold")).lower()
    if action not in {"buy", "sell", "hold", "reduce", "emergency_exit"}:
        action = "hold"
    time_horizon = str(payload.get("time_horizon", "15m"))
    if time_horizon not in {"5m", "15m", "1h"}:
        time_horizon = "15m"
    data_quality = str(payload.get("data_quality", "degraded"))
    if data_quality not in {"good", "degraded", "bad"}:
        data_quality = "degraded"
    confidence = min(1.0, max(0.0, _number(payload.get("confidence"), 0.0)))
    suggested_position_pct = min(1.0, max(0.0, _number(payload.get("suggested_position_pct"), 0.0)))
    reason_codes = payload.get("reason_codes", ["model_output"])
    invalidators = payload.get("invalidators", [])
    if isinstance(reason_codes, str):
        reason_codes = [reason_codes]
    elif not isinstance(reason_codes, list):
        reason_codes = ["model_output"]
    reason_codes = [str(code) for code in reason_codes if code is not None] or ["model_output"]
    if isinstance(invalidators, str):
        invalidators = [invalidators]
    elif not isinstance(invalidators, list):
        invalidators = []
    invalidators = [str(value) for value in invalidators if value is not None]
    payload.update({
        "agent_name": agent_name,
        "symbol": snapshot.get("symbol", ""),
        "action": action,
        "confidence": confidence,
        "time_horizon": time_horizon,
        "entry_price": _optional_number(payload.get("entry_price")),
        "stop_loss_price": _optional_number(payload.get("stop_loss_price")),
        "take_profit_price": _optional_number(payload.get("take_profit_price")),
        "suggested_position_pct": suggested_position_pct,
        "reason_codes": reason_codes,
        "invalidators": invalidators,
        "data_quality": data_quality,
        "veto": payload.get("veto") is True,
    })
    return AgentDecision.model_validate(payload)

class OpenAIAgent:
    def __init__(self, name, api_key, model="gpt-5.4-mini", timeout=20, retries=2,
                 input_cost_per_million=0.75, output_cost_per_million=4.50):
        self.name=name; self.key=api_key; self.model=model; self.timeout=timeout; self.retries=retries
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.last_usage = {}
        self.last_cost_usd = 0.0
        self.last_attempts = 0
        self.last_error = ""
        self.last_response_preview = ""

    def _record_usage(self, usage):
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
        output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        self.last_usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        self.last_cost_usd = round(
            input_tokens * self.input_cost_per_million / 1_000_000
            + output_tokens * self.output_cost_per_million / 1_000_000,
            10,
        )

    async def decide(self, snapshot):
        self.last_usage = {}
        self.last_cost_usd = 0.0
        self.last_attempts = 0
        self.last_error = ""
        self.last_response_preview = ""
        if not self.key: return hold(self.name,snapshot.get("symbol",""),"openai_key_missing")
        safe_snapshot = sanitize_snapshot(snapshot)
        payload={"model":self.model,"input":[{"role":"system","content":PROMPTS[self.name]+SYSTEM_SUFFIX},{"role":"user","content":json.dumps(safe_snapshot,separators=(",",":"))}],"text":{"format":{"type":"json_object"}},"store":False}
        last_error = None
        for attempt in range(self.retries + 1):
            self.last_attempts = attempt + 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    r=await c.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {self.key}"},json=payload); r.raise_for_status(); data=r.json()
                usage = data.get("usage", {})
                self._record_usage(usage)
                if usage:
                    log.info("openai_usage", extra={"agent": self.name, "model": self.model, "usage": usage})
                text = _response_text(data)
                self.last_response_preview = text[:500]
                return _normalize_decision(text, self.name, snapshot)
            except (httpx.TimeoutException, TimeoutError) as exc:
                last_error = exc
                failure_reason = "openai_timeout"
                if attempt < self.retries:
                    await asyncio.sleep(min(4, 2**attempt))
            except httpx.HTTPStatusError as exc:
                last_error = exc
                failure_reason = "openai_http_error"
                if attempt < self.retries:
                    await asyncio.sleep(min(4, 2**attempt))
            except httpx.HTTPError as exc:
                last_error = exc
                failure_reason = "openai_transport_error"
                if attempt < self.retries:
                    await asyncio.sleep(min(4, 2**attempt))
            except json.JSONDecodeError as exc:
                last_error = exc
                failure_reason = "openai_invalid_json"
                if attempt < self.retries:
                    await asyncio.sleep(min(4, 2**attempt))
            except ValidationError as exc:
                last_error = exc
                failure_reason = "openai_schema_error"
                self.last_error = "; ".join(
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.errors()
                )
                if attempt < self.retries:
                    await asyncio.sleep(min(4, 2**attempt))
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                last_error = exc
                failure_reason = "openai_invalid_response"
                if attempt < self.retries:
                    await asyncio.sleep(min(4, 2**attempt))
        self.last_error = self.last_error or str(last_error)
        log.warning("openai_agent_hold", extra={"agent": self.name, "error": self.last_error})
        return hold(self.name,snapshot.get("symbol",""),failure_reason)
