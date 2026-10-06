"""Turns a parsed strategy graph into a StrategyValidationResult.

Baseline structural checks (duplicate ids, dangling edges, self-loops) come
from the parser. This module adds everything that requires knowledge of node
types: unknown node types, per-node param validation, input arity, cycle
detection, and reachability — plus a few "the frontend UI can legally draw
this, but it's semantically odd" cases that are reported as warnings rather
than errors so they never block saving a strategy.
"""
from collections import deque

from app.schemas.strategy import StrategyGraph, StrategyValidationResult, ValidationIssue
from app.strategy_engine.nodes.base import GATE_CATEGORIES, NodeCategory, SOURCE_CATEGORIES, TERMINAL_CATEGORIES
from app.strategy_engine.nodes.registry import get_node_definition, is_known_node_type
from app.strategy_engine.parser import ParsedGraph, parse_graph


def validate_strategy_graph(graph: StrategyGraph) -> StrategyValidationResult:
    parse_result = parse_graph(graph)
    parsed = parse_result.graph
    issues: list[ValidationIssue] = list(parse_result.issues)

    if not parsed.nodes:
        issues.append(ValidationIssue(code="EMPTY_GRAPH", message="Strategy has no nodes", severity="error"))
        return _finalize(issues)

    for node in parsed.nodes.values():
        if not is_known_node_type(node.node_type):
            issues.append(
                ValidationIssue(
                    node_id=node.id,
                    code="UNKNOWN_NODE_TYPE",
                    message=f"Unknown node type '{node.node_type}'",
                    severity="error",
                )
            )

    for node in parsed.nodes.values():
        definition = get_node_definition(node.node_type)
        if definition is None:
            continue

        for message in definition.validate_params(node.params):
            issues.append(
                ValidationIssue(node_id=node.id, code="INVALID_PARAMS", message=message, severity="error")
            )

        min_inputs, max_inputs = definition.input_arity(node.params)
        n_in = len(parsed.incoming.get(node.id, []))
        if node.node_type == "condition" and node.params.get("operator") in {"crosses_above", "crosses_below"}:
            ports = [edge.target_handle for edge in graph.edges if edge.target == node.id]
            if any(port in {"left", "right"} for port in ports) and sorted(str(port) for port in ports) != ["left", "right"]:
                issues.append(ValidationIssue(node_id=node.id, code="INVALID_CROSSOVER_PORTS",
                    message="Crossover needs one connection to A (left) and one to B (right)", severity="error"))
        if n_in < min_inputs:
            issues.append(
                ValidationIssue(
                    node_id=node.id,
                    code="MISSING_INPUT",
                    message=f"'{node.label}' requires at least {min_inputs} input(s) but has {n_in}",
                    severity="error",
                )
            )
        if max_inputs is not None and n_in > max_inputs:
            issues.append(
                ValidationIssue(
                    node_id=node.id,
                    code="TOO_MANY_INPUTS",
                    message=f"'{node.label}' accepts at most {max_inputs} input(s) but has {n_in}",
                    severity="error",
                )
            )

        if definition.category in TERMINAL_CATEGORIES and parsed.outgoing.get(node.id):
            issues.append(
                ValidationIssue(
                    node_id=node.id,
                    code="TERMINAL_NODE_HAS_OUTGOING_EDGE",
                    message=(
                        f"'{node.label}' is a {definition.category.value} node — its outgoing "
                        "connection(s) will be ignored during execution"
                    ),
                    severity="warning",
                )
            )

        if definition.category == NodeCategory.RISK:
            upstream_ids = parsed.incoming.get(node.id, [])
            has_gate = any(
                (up_def := get_node_definition(parsed.nodes[up_id].node_type)) is not None
                and up_def.category in GATE_CATEGORIES
                for up_id in upstream_ids
                if up_id in parsed.nodes
            )
            if upstream_ids and not has_gate:
                issues.append(
                    ValidationIssue(
                        node_id=node.id,
                        code="RISK_NODE_NO_CONDITION_UPSTREAM",
                        message=f"'{node.label}' is not gated by a condition/logic node upstream",
                        severity="warning",
                    )
                )

    for target_id, incoming in parsed.incoming.items():
        target = get_node_definition(parsed.nodes[target_id].node_type)
        if target is None:
            continue
        for source_id in incoming:
            source = get_node_definition(parsed.nodes[source_id].node_type)
            if source is None:
                continue
            if target.category in {NodeCategory.ACTION, NodeCategory.RISK, NodeCategory.LOGIC} and source.category not in GATE_CATEGORIES:
                issues.append(ValidationIssue(node_id=target_id, code="INVALID_CONNECTION",
                    message="Actions, risk and logic nodes require boolean condition/logic inputs", severity="error"))
            if target.category in {NodeCategory.CONDITION, NodeCategory.INDICATOR} and source.category not in SOURCE_CATEGORIES:
                issues.append(ValidationIssue(node_id=target_id, code="INVALID_CONNECTION",
                    message="Conditions and indicators require numeric source inputs", severity="error"))

    cycle_node_ids = _find_cycle_nodes(parsed)
    if cycle_node_ids:
        issues.append(
            ValidationIssue(
                code="CYCLE_DETECTED",
                message="Strategy graph contains a cycle involving node(s): " + ", ".join(sorted(cycle_node_ids)),
                severity="error",
            )
        )

    reachable_actions = _find_reachable_actions(parsed)
    if not reachable_actions:
        issues.append(
            ValidationIssue(
                code="NO_REACHABLE_ACTION",
                message=(
                    "Strategy has no BUY/SELL/HOLD action reachable from a data, indicator, "
                    "or sentiment node — it would never trade"
                ),
                severity="error",
            )
        )

    return _finalize(issues)


def _finalize(issues: list[ValidationIssue]) -> StrategyValidationResult:
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    return StrategyValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def _find_cycle_nodes(graph: ParsedGraph) -> list[str]:
    """Kahn's algorithm: whatever nodes are left with unresolved in-degree
    once no more zero-in-degree nodes remain are part of (or downstream of) a
    cycle."""
    in_degree = {node_id: 0 for node_id in graph.nodes}
    for node_id in graph.nodes:
        for target in graph.outgoing.get(node_id, []):
            if target in in_degree:
                in_degree[target] += 1

    queue = deque(node_id for node_id, degree in in_degree.items() if degree == 0)
    remaining = dict(in_degree)
    visited = 0

    while queue:
        node_id = queue.popleft()
        visited += 1
        for target in graph.outgoing.get(node_id, []):
            if target not in remaining:
                continue
            remaining[target] -= 1
            if remaining[target] == 0:
                queue.append(target)

    if visited == len(graph.nodes):
        return []
    return [node_id for node_id, degree in remaining.items() if degree > 0]


def _find_reachable_actions(graph: ParsedGraph) -> set[str]:
    source_ids = [
        node.id
        for node in graph.nodes.values()
        if (definition := get_node_definition(node.node_type)) is not None and definition.category in SOURCE_CATEGORIES
    ]

    visited: set[str] = set(source_ids)
    queue = deque(source_ids)
    while queue:
        node_id = queue.popleft()
        for target in graph.outgoing.get(node_id, []):
            if target in graph.nodes and target not in visited:
                visited.add(target)
                queue.append(target)

    action_ids = {
        node.id
        for node in graph.nodes.values()
        if (definition := get_node_definition(node.node_type)) is not None and definition.category == NodeCategory.ACTION
    }
    return visited & action_ids
