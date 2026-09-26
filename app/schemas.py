from typing import Any, Optional
from pydantic import BaseModel, Field


class LineInterpretation(BaseModel):
    raw_text: str
    quantity: int = Field(gt=0)
    sku: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    reason: str


class CatalogMatch(BaseModel):
    sku: Optional[str]
    name: Optional[str]
    confidence: float = Field(ge=0, le=1)
    match_type: str
    reason: str


class LineDecision(BaseModel):
    raw_text: str
    quantity: int
    sku: Optional[str]
    catalog_name: Optional[str]
    reconciliation_confidence: float
    inventory_source: str
    decision: str
    reason: str


class OrderDecision(BaseModel):
    order_id: str
    status: str
    risk_level: str
    auto_dispatch_allowed: bool
    total_value: float
    line_decisions: list[LineDecision]
    actions: list[dict[str, Any]]
    review_required: bool
    summary: str


class LineCorrection(BaseModel):
    raw_text: str
    sku: str


class OverrideRequest(BaseModel):
    decision: str
    reason: str
    line_corrections: list[LineCorrection] = Field(default_factory=list)
