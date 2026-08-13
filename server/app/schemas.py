"""Pydantic request/response models for the scan API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

PIPELINE_TYPES = ("daily_ep_scan", "daily_vcp_scan", "daily_bo_scan")


class RunCreate(BaseModel):
    """Body for POST /api/runs."""

    name: str = Field(default="scan", max_length=120)
    pipeline_type: str = "daily_bo_scan"
    force_symbols: str
    select: str = "strict"  # EP only: baseline | strict | both
    run_catalyst: bool = True
    apply_gates: bool = True
    bo_profile: str = "best"  # BO only: best | moderate-lose | widen

    @field_validator("force_symbols")
    @classmethod
    def _symbols_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("force_symbols is required")
        return v

    @field_validator("pipeline_type")
    @classmethod
    def _known_pipeline(cls, v: str) -> str:
        if v not in PIPELINE_TYPES:
            raise ValueError(f"unknown pipeline_type: {v}")
        return v
