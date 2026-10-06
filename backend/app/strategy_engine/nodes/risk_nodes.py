from pydantic import BaseModel, ConfigDict, Field

from app.strategy_engine.nodes.base import NodeCategory, NodeDefinition


class RiskParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    percent: float = Field(gt=0, le=100)


class StopLossNode(NodeDefinition):
    """A terminal node, same as BUY/SELL — evaluated from its own upstream
    trigger. The frontend wires it as a sibling of BUY off a shared
    condition (risk management attached to whatever position that condition
    opens), not as a child of BUY."""

    node_type = "stopLoss"
    category = NodeCategory.RISK
    label = "Stop Loss"
    params_model = RiskParams
    default_min_inputs = 1
    default_max_inputs = 1


class TakeProfitNode(NodeDefinition):
    node_type = "takeProfit"
    category = NodeCategory.RISK
    label = "Take Profit"
    params_model = RiskParams
    default_min_inputs = 1
    default_max_inputs = 1
