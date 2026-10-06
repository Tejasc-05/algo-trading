from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.strategy_engine.nodes.base import NodeCategory, NodeDefinition


class SentimentParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    threshold: float = Field(default=70, ge=0, le=100)
    source: str = Field(default="AI", max_length=64)
    label: Literal["positive", "negative", "neutral"] | None = None


class SentimentNode(NodeDefinition):
    """A source node: fetches a sentiment score for the strategy's symbol
    (see app.sentiment) rather than deriving one from upstream nodes."""

    node_type = "sentiment"
    category = NodeCategory.SENTIMENT
    label = "Sentiment"
    params_model = SentimentParams
    default_min_inputs = 0
    default_max_inputs = 0
