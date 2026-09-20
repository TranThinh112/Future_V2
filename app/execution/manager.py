import time
import uuid

from app.execution.proposal import normalize_order


class OrderManager:
    def __init__(self, mode="paper", ttl_seconds=300): self.mode=mode; self.active={}; self.ttl_seconds=ttl_seconds
    async def submit(self, proposal, instrument=None):
        if self.mode=="live": raise RuntimeError("live execution requires explicit operator gate")
        proposal = dict(proposal)
        if "client_order_id" not in proposal:
            proposal["client_order_id"] = "cli-" + uuid.uuid4().hex[:24]
        if instrument and "price" in proposal and "size" in proposal:
            price, size = normalize_order(proposal["price"], proposal["size"], instrument)
            proposal["price"] = float(price)
            proposal["size"] = float(size)
        proposal.setdefault("decision_id", proposal["client_order_id"])
        proposal.setdefault("agent_votes", [])
        proposal.setdefault("consensus", {})
        proposal.setdefault("risk_result", {})
        proposal.setdefault("created_at_ms", int(time.time() * 1000))
        key=(proposal.get("symbol"),proposal.get("side"),proposal.get("client_order_id"))
        now=time.monotonic(); self.active={k:v for k,v in self.active.items() if now-v<self.ttl_seconds}
        if key in self.active: raise ValueError("duplicate_order")
        order_id = "paper-"+uuid.uuid4().hex
        self.active[key]=now; return {"order_id": order_id, "status":"simulated", "filled_size":proposal.get("size",0), "proposal":proposal, "audit": {"decision_id": proposal["decision_id"], "client_order_id": proposal["client_order_id"], "order_id": order_id, "agent_votes": proposal["agent_votes"], "consensus": proposal["consensus"], "risk_result": proposal["risk_result"], "created_at_ms": proposal["created_at_ms"], "updated_at_ms": int(time.time() * 1000)}}
    def protective_orders(self, proposal):
        return [{"type":"stop-loss","price":proposal["stop_loss_price"]},{"type":"take-profit","price":proposal["take_profit_price"]}]
