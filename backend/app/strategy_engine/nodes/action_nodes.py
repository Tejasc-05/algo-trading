from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.strategy_engine.nodes.base import EmptyParams, NodeCategory, NodeDefinition


class ActionParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    amount: float = Field(gt=0)
    type: Literal["market", "limit"] = "market"
    limit_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_limit_price(self):
        if self.type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required when type='limit'")
        return self


class BuyNode(NodeDefinition):
    node_type = "buy"
    category = NodeCategory.ACTION
    label = "Buy"
    params_model = ActionParams
    default_min_inputs = 1
    default_max_inputs = 1


class SellNode(NodeDefinition):
    node_type = "sell"
    category = NodeCategory.ACTION
    label = "Sell"
    params_model = ActionParams
    default_min_inputs = 1
    default_max_inputs = 1


class HoldNode(NodeDefinition):
    node_type = "hold"
    category = NodeCategory.ACTION
    label = "Hold"
    params_model = EmptyParams
    default_min_inputs = 1
    default_max_inputs = 1


class OpenLongNode(BuyNode):
    node_type = "openLong"
    label = "Open Futures Long"


class OpenShortNode(BuyNode):
    node_type = "openShort"
    label = "Open Futures Short"


class ClosePositionNode(HoldNode):
    node_type = "closePosition"
    label = "Close Futures Position"
