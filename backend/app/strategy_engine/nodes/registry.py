"""Central lookup of every known node type. Adding a new block to the
platform means adding one NodeDefinition subclass and one line here — nothing
in parser.py or validator.py needs to change."""
from app.strategy_engine.nodes.action_nodes import BuyNode, HoldNode, SellNode, OpenLongNode, OpenShortNode, ClosePositionNode
from app.strategy_engine.nodes.base import NodeDefinition
from app.strategy_engine.nodes.condition_nodes import ConditionNode
from app.strategy_engine.nodes.data_nodes import PriceNode, VolumeNode
from app.strategy_engine.nodes.indicator_nodes import (
    BollingerBandsNode,
    EMANode,
    MACDNode,
    MovingAverageNode,
    RSINode,
    SMANode,
)
from app.strategy_engine.nodes.logic_nodes import AndNode, NotNode, OrNode
from app.strategy_engine.nodes.risk_nodes import StopLossNode, TakeProfitNode
from app.strategy_engine.nodes.sentiment_nodes import SentimentNode

NODE_REGISTRY: dict[str, type[NodeDefinition]] = {
    node_cls.node_type: node_cls
    for node_cls in (
        PriceNode,
        VolumeNode,
        RSINode,
        SMANode,
        EMANode,
        MACDNode,
        MovingAverageNode,
        BollingerBandsNode,
        ConditionNode,
        AndNode,
        OrNode,
        NotNode,
        SentimentNode,
        BuyNode,
        SellNode,
        HoldNode,
        OpenLongNode,
        OpenShortNode,
        ClosePositionNode,
        StopLossNode,
        TakeProfitNode,
    )
}


def get_node_definition(node_type: str) -> type[NodeDefinition] | None:
    return NODE_REGISTRY.get(node_type)


def is_known_node_type(node_type: str) -> bool:
    return node_type in NODE_REGISTRY
