from __future__ import annotations

from pydantic import BaseModel, Field


class ExplanationItem(BaseModel):
    product_id: str
    headline: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    recommendation_reason: str = ""


class ExplanationOutput(BaseModel):
    summary: str = ""
    items: list[ExplanationItem] = Field(default_factory=list)
