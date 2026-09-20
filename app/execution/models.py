from pydantic import BaseModel, Field


class OrderProposal(BaseModel):
    decision_id: str; symbol: str; side: str; price: float = Field(gt=0); size: float = Field(gt=0)
    stop_loss_price: float = Field(gt=0); take_profit_price: float = Field(gt=0); client_order_id: str
class Fill(BaseModel):
    order_id: str; symbol: str; side: str; price: float; size: float; fee: float; timestamp_ms: int
