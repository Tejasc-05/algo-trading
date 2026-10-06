"""Pydantic mirror of the React Flow graph shape the strategy builder already
produces (see src/store/useStrategyStore.ts and
src/features/strategy-builder/nodes/StrategyNodes.tsx in the frontend).

Node/edge field names on the wire match the frontend exactly (camelCase);
`populate_by_name=True` lets backend code use idiomatic snake_case internally.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ParamValue = str | float | int


class ReactFlowPosition(BaseModel):
    x: float = 0
    y: float = 0


class StrategyNodeData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, allow_inf_nan=False)

    label: str
    node_type: str = Field(alias="nodeType")
    params: dict[str, ParamValue] = Field(default_factory=dict)


class ReactFlowNode(BaseModel):
    """A single strategy-builder node. `type` is React Flow's own field (used
    to pick the rendering component) and is expected to match `data.nodeType`
    — both are sent by the frontend today; `data.node_type` is treated as the
    authoritative value for backend node-registry lookups."""

    id: str
    type: str | None = None
    position: ReactFlowPosition = Field(default_factory=ReactFlowPosition)
    data: StrategyNodeData


class ReactFlowEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True, allow_inf_nan=False)
    source_handle: str | None = Field(default=None, alias="sourceHandle")
    target_handle: str | None = Field(default=None, alias="targetHandle")
    id: str | None = None
    source: str
    target: str
    animated: bool | None = None


class StrategyGraph(BaseModel):
    nodes: list[ReactFlowNode] = Field(default_factory=list, max_length=256)
    edges: list[ReactFlowEdge] = Field(default_factory=list, max_length=1024)


# --- Requests --------------------------------------------------------------

class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    graph: StrategyGraph


class StrategyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    graph: StrategyGraph


class StrategyValidateRequest(BaseModel):
    """Optional: validate an in-progress (unsaved) graph. If omitted, the
    endpoint validates the strategy's current saved version instead."""

    graph: StrategyGraph | None = None


# --- Responses ---------------------------------------------------------

class StrategyVersionOut(BaseModel):
    id: str
    version_number: int
    graph: StrategyGraph
    created_at: datetime


class StrategySummaryOut(BaseModel):
    id: str
    name: str
    description: str | None
    current_version: int
    created_at: datetime
    updated_at: datetime


class StrategyDetailOut(StrategySummaryOut):
    versions: list[StrategyVersionOut] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    node_id: str | None = None
    code: str
    message: str
    severity: Literal["error", "warning"]


class StrategyValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
