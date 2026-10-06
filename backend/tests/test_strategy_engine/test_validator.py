"""Pure-Python tests for strategy graph validation — no FastAPI/DB involved."""
from app.schemas.strategy import StrategyGraph
from app.strategy_engine.validator import validate_strategy_graph


def _node(node_id: str, node_type: str, params: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "data": {"label": node_type, "nodeType": node_type, "params": params or {}},
    }


def _edge(edge_id: str, source: str, target: str) -> dict:
    return {"id": edge_id, "source": source, "target": target}


def test_the_real_store_example_graph_is_fully_valid():
    """rsi-1 -> condition-1 -> {buy-1, stopLoss-1}, exactly as shipped in
    src/store/useStrategyStore.ts. Must validate clean: no errors, no
    warnings."""
    graph = StrategyGraph.model_validate(
        {
            "nodes": [
                _node("rsi-1", "rsi", {"period": 14, "oversold": 30, "overbought": 70}),
                _node("condition-1", "condition", {"operator": "<", "value": 30}),
                _node("buy-1", "buy", {"amount": 0.1, "type": "market"}),
                _node("stopLoss-1", "stopLoss", {"percent": 2}),
            ],
            "edges": [
                _edge("e1", "rsi-1", "condition-1"),
                _edge("e2", "condition-1", "buy-1"),
                _edge("e3", "condition-1", "stopLoss-1"),
            ],
        }
    )

    result = validate_strategy_graph(graph)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


def test_simple_valid_graph():
    graph = StrategyGraph.model_validate(
        {
            "nodes": [
                _node("rsi-1", "rsi"),
                _node("condition-1", "condition", {"operator": ">", "value": 70}),
                _node("sell-1", "sell", {"amount": 0.1}),
            ],
            "edges": [_edge("e1", "rsi-1", "condition-1"), _edge("e2", "condition-1", "sell-1")],
        }
    )
    result = validate_strategy_graph(graph)
    assert result.valid is True


def test_cycle_is_detected():
    graph = StrategyGraph.model_validate(
        {
            "nodes": [
                _node("c1", "condition", {"operator": ">", "value": 0}),
                _node("c2", "condition", {"operator": ">", "value": 0}),
            ],
            "edges": [_edge("e1", "c1", "c2"), _edge("e2", "c2", "c1")],
        }
    )
    result = validate_strategy_graph(graph)
    assert result.valid is False
    assert any(issue.code == "CYCLE_DETECTED" for issue in result.errors)


def test_missing_input_on_action_node_is_detected():
    graph = StrategyGraph.model_validate(
        {"nodes": [_node("buy-1", "buy", {"amount": 0.1})], "edges": []}
    )
    result = validate_strategy_graph(graph)
    assert result.valid is False
    assert any(issue.code == "MISSING_INPUT" and issue.node_id == "buy-1" for issue in result.errors)


def test_unknown_node_type_is_detected():
    graph = StrategyGraph.model_validate({"nodes": [_node("weird-1", "not_a_real_node_type")], "edges": []})
    result = validate_strategy_graph(graph)
    assert result.valid is False
    assert any(issue.code == "UNKNOWN_NODE_TYPE" and issue.node_id == "weird-1" for issue in result.errors)


def test_orphan_node_with_no_connections_is_detected():
    """A properly wired chain plus one extra node dropped on the canvas but
    never connected to anything."""
    graph = StrategyGraph.model_validate(
        {
            "nodes": [
                _node("rsi-1", "rsi"),
                _node("condition-1", "condition", {"operator": "<", "value": 30}),
                _node("buy-1", "buy", {"amount": 0.1}),
                _node("orphan-condition", "condition", {"operator": ">", "value": 50}),
            ],
            "edges": [_edge("e1", "rsi-1", "condition-1"), _edge("e2", "condition-1", "buy-1")],
        }
    )
    result = validate_strategy_graph(graph)
    assert result.valid is False
    assert any(
        issue.code == "MISSING_INPUT" and issue.node_id == "orphan-condition" for issue in result.errors
    )


def test_invalid_params_are_detected():
    graph = StrategyGraph.model_validate({"nodes": [_node("rsi-1", "rsi", {"period": -5})], "edges": []})
    result = validate_strategy_graph(graph)
    assert result.valid is False
    assert any(issue.code == "INVALID_PARAMS" and issue.node_id == "rsi-1" for issue in result.errors)


def test_strategy_with_no_reachable_action_is_invalid():
    graph = StrategyGraph.model_validate(
        {"nodes": [_node("rsi-1", "rsi"), _node("condition-1", "condition", {"operator": "<", "value": 30})],
         "edges": [_edge("e1", "rsi-1", "condition-1")]}
    )
    result = validate_strategy_graph(graph)
    assert result.valid is False
    assert any(issue.code == "NO_REACHABLE_ACTION" for issue in result.errors)


def test_risk_node_without_condition_upstream_is_a_warning():
    graph = StrategyGraph.model_validate(
        {
            "nodes": [
                _node("rsi-1", "rsi"),
                _node("condition-1", "condition", {"operator": "<", "value": 30}),
                _node("buy-1", "buy", {"amount": 0.1}),
                _node("stopLoss-1", "stopLoss", {"percent": 2}),
            ],
            "edges": [
                _edge("e1", "rsi-1", "condition-1"),
                _edge("e2", "condition-1", "buy-1"),
                # stop-loss wired straight to the indicator, skipping the condition gate
                _edge("e3", "rsi-1", "stopLoss-1"),
            ],
        }
    )
    result = validate_strategy_graph(graph)
    assert result.valid is False  # Numeric indicator output cannot safely gate risk execution
    assert any(issue.code == "INVALID_CONNECTION" for issue in result.errors)
    assert any(issue.code == "RISK_NODE_NO_CONDITION_UPSTREAM" for issue in result.warnings)
