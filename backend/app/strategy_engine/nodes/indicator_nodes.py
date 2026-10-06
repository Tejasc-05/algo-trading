from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.strategy_engine.nodes.base import NodeCategory, NodeDefinition


class RSIParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    period: int = Field(default=14, gt=1, le=200)
    oversold: float | None = Field(default=None, ge=0, le=100)
    overbought: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def check_thresholds(self):
        if self.oversold is not None and self.overbought is not None and self.oversold >= self.overbought:
            raise ValueError("oversold must be less than overbought")
        return self


class RSINode(NodeDefinition):
    node_type = "rsi"
    category = NodeCategory.INDICATOR
    label = "RSI"
    params_model = RSIParams
    default_min_inputs = 0
    default_max_inputs = 0


class MovingAverageParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    period: int = Field(default=50, gt=1, le=500)
    type: Literal["SMA", "EMA"] = "SMA"


class MovingAverageNode(NodeDefinition):
    """Matches the frontend's single `movingAverage` node; `params.type`
    selects SMA vs. EMA computation in the Phase-4 executor."""

    node_type = "movingAverage"
    category = NodeCategory.INDICATOR
    label = "Moving Average"
    params_model = MovingAverageParams
    default_min_inputs = 0
    default_max_inputs = 0


class PeriodParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    period: int = Field(default=20, gt=1, le=500)


class SMANode(NodeDefinition):
    """Standalone SMA node — not emitted by the frontend yet, available for
    future use without a schema change."""

    node_type = "sma"
    category = NodeCategory.INDICATOR
    label = "Simple Moving Average"
    params_model = PeriodParams
    default_min_inputs = 0
    default_max_inputs = 0


class EMANode(NodeDefinition):
    node_type = "ema"
    category = NodeCategory.INDICATOR
    label = "Exponential Moving Average"
    params_model = PeriodParams
    default_min_inputs = 0
    default_max_inputs = 0


class MACDParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    fast: int = Field(default=12, gt=0, le=200)
    slow: int = Field(default=26, gt=0, le=500)
    signal: int = Field(default=9, gt=0, le=200)
    output: Literal["macd", "signal", "histogram"] = "macd"

    @model_validator(mode="after")
    def check_fast_lt_slow(self):
        if self.fast >= self.slow:
            raise ValueError("fast period must be less than slow period")
        return self


class MACDNode(NodeDefinition):
    node_type = "macd"
    category = NodeCategory.INDICATOR
    label = "MACD"
    params_model = MACDParams
    default_min_inputs = 0
    default_max_inputs = 0


class BollingerBandsParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    period: int = Field(default=20, gt=1, le=500)
    std_dev: float = Field(default=2.0, gt=0, le=10)


class BollingerBandsNode(NodeDefinition):
    node_type = "bollinger_bands"
    category = NodeCategory.INDICATOR
    label = "Bollinger Bands"
    params_model = BollingerBandsParams
    default_min_inputs = 0
    default_max_inputs = 0
