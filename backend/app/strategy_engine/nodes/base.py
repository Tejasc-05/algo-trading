"""The node-definition contract every strategy-builder block implements.

A NodeDefinition never executes user-supplied code — it only declares
metadata (category, how many inputs it accepts, a Pydantic model for its
`params`) and, from Phase 4 onward, a pure-Python `evaluate()` that computes
its output from already-fetched market data. There is no eval()/exec()
anywhere in this pipeline.
"""
from abc import ABC
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError


class NodeCategory(str, Enum):
    DATA = "data"
    INDICATOR = "indicator"
    CONDITION = "condition"
    LOGIC = "logic"
    SENTIMENT = "sentiment"
    ACTION = "action"
    RISK = "risk"


# Categories with no inputs — they originate a value (from market data,
# a sentiment provider, etc.) rather than deriving one from upstream nodes.
SOURCE_CATEGORIES = {NodeCategory.DATA, NodeCategory.INDICATOR, NodeCategory.SENTIMENT}

# Categories that consume upstream values and produce a boolean.
GATE_CATEGORIES = {NodeCategory.CONDITION, NodeCategory.LOGIC}

# Categories that are graph terminals (an executable strategy must be able to
# reach at least one of these from a source node).
TERMINAL_CATEGORIES = {NodeCategory.ACTION, NodeCategory.RISK}


class EmptyParams(BaseModel):
    """Used by node types that take no configuration."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class NodeDefinition(ABC):
    """Base class for every node type. Subclasses set the ClassVars and,
    where arity depends on a parameter (e.g. a condition's operator), override
    `input_arity`."""

    node_type: ClassVar[str]
    category: ClassVar[NodeCategory]
    label: ClassVar[str] = ""
    params_model: ClassVar[type[BaseModel]] = EmptyParams

    # Static default; override per-instance via input_arity() when arity
    # depends on params (e.g. condition operator, AND/OR fan-in).
    default_min_inputs: ClassVar[int] = 0
    default_max_inputs: ClassVar[int | None] = 0

    @classmethod
    def validate_params(cls, params: dict[str, Any]) -> list[str]:
        try:
            cls.params_model.model_validate(params)
        except ValidationError as exc:
            messages = []
            for error in exc.errors():
                location = ".".join(str(part) for part in error["loc"])
                messages.append(f"{location}: {error['msg']}" if location else error["msg"])
            return messages
        return []

    @classmethod
    def input_arity(cls, params: dict[str, Any]) -> tuple[int, int | None]:
        """Returns (min_inputs, max_inputs). max_inputs=None means unlimited."""
        return cls.default_min_inputs, cls.default_max_inputs

    def evaluate(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            f"Evaluation for node type '{self.node_type}' is implemented in Phase 4 "
            "(app.strategy_engine.executor)."
        )
