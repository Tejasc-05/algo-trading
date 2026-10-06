from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.strategy_engine.nodes.base import NodeCategory, NodeDefinition

CROSS_OPERATORS = {"crosses_above", "crosses_below"}
COMPARISON_OPERATORS = {"<", ">", "<=", ">=", "==", "!="}


class ConditionParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    operator: Literal["<", ">", "<=", ">=", "==", "!=", "crosses_above", "crosses_below"]
    value: float | None = None

    @model_validator(mode="after")
    def check_value_required(self):
        if self.operator in COMPARISON_OPERATORS and self.value is None:
            raise ValueError(f"'value' is required for comparison operator '{self.operator}'")
        return self


class ConditionNode(NodeDefinition):
    """Comparison operators (<, >, <=, >=, ==, !=) compare one upstream
    series against a literal `params.value` and need exactly 1 input.
    crosses_above/crosses_below compare two upstream series against each
    other (e.g. Price crosses_above a moving average) and need exactly 2."""

    node_type = "condition"
    category = NodeCategory.CONDITION
    label = "Condition"
    params_model = ConditionParams

    @classmethod
    def input_arity(cls, params: dict[str, Any]) -> tuple[int, int | None]:
        if params.get("operator") in CROSS_OPERATORS:
            return 2, 2
        return 1, 1
