"""Pydantic request/response models for the scan API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

PIPELINE_TYPES = (
    "daily_ep_scan",
    "daily_vcp_scan",
    "daily_bo_scan",
    "daily_zhao_scan",
    "daily_premarket_scan",
)
UNIVERSE_SOURCES = ("paste", "snapshot")


class RunCreate(BaseModel):
    """Body for POST /api/runs.

    Legacy path: ``pipeline_type`` + ``force_symbols``/``use_screener``.
    Component-graph path (T22): ``definition_id`` or inline ``graph``, plus
    per-run ``universe_source``/``universe_scan_id`` and ``node_overrides``.
    """

    name: str = Field(default="scan", max_length=120)
    pipeline_type: str = "daily_bo_scan"
    force_symbols: str = ""
    use_screener: bool = False  # True = market-wide snapshot sweep (no paste list)
    select: str = "strict"  # EP only: baseline | strict | both
    run_catalyst: bool = True
    apply_gates: bool = True
    bo_profile: str = "best"  # BO only: best | moderate-lose | widen

    # Component graph (T22)
    definition_id: Optional[str] = None
    graph: Optional[dict[str, Any]] = None  # inline canvas graph JSON
    universe_source: str = "paste"
    universe_scan_id: Optional[str] = None
    node_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("pipeline_type")
    @classmethod
    def _known_pipeline(cls, v: str) -> str:
        if v not in PIPELINE_TYPES:
            raise ValueError(f"unknown pipeline_type: {v}")
        return v

    @field_validator("universe_source")
    @classmethod
    def _known_universe_source(cls, v: str) -> str:
        if v not in UNIVERSE_SOURCES:
            raise ValueError(f"unknown universe_source: {v}")
        return v

    @model_validator(mode="after")
    def _validate_run(self) -> "RunCreate":
        is_graph = self.definition_id is not None or self.graph is not None
        if is_graph:
            return self
        if not self.use_screener and not self.force_symbols.strip():
            raise ValueError("force_symbols is required when use_screener is false")
        return self


class DefinitionCreate(BaseModel):
    """Body for POST /api/definitions."""

    name: str = Field(min_length=1, max_length=120)
    graph: dict[str, Any]


class DefinitionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    graph: dict[str, Any]


class ComponentTemplateCreate(BaseModel):
    """Body for POST /api/component-templates."""

    name: str = Field(min_length=1, max_length=120)
    component_id: str = Field(min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)


class ComponentTemplateUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    component_id: str = Field(min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)


CONTROL_ACTIONS = ("skip", "pause", "resume", "cancel", "confirm")
CONFIRM_DECISIONS = ("proceed", "skip", "cancel")


class ControlRequest(BaseModel):
    """Body for POST /api/runs/{id}/control."""

    action: str
    node_id: Optional[str] = None
    decision: Optional[str] = None

    @field_validator("action")
    @classmethod
    def _known_action(cls, v: str) -> str:
        if v not in CONTROL_ACTIONS:
            raise ValueError(f"unknown control action: {v}")
        return v

    @field_validator("decision")
    @classmethod
    def _known_decision(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CONFIRM_DECISIONS:
            raise ValueError(f"unknown confirm decision: {v}")
        return v

    @model_validator(mode="after")
    def _validate(self) -> "ControlRequest":
        if self.action in ("skip", "confirm") and not self.node_id:
            raise ValueError(f"{self.action} requires node_id")
        if self.action == "confirm" and self.decision is None:
            raise ValueError("confirm requires decision")
        return self
