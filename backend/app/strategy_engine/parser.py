"""Converts the frontend's React Flow JSON into a small internal graph
structure and catches structural problems (duplicate ids, dangling edges,
self-loops) before semantic validation runs. This is the only place that
reads the raw graph — everything downstream works off ParsedGraph.
"""
from dataclasses import dataclass, field

from app.schemas.strategy import StrategyGraph, ValidationIssue


@dataclass
class ParsedNode:
    id: str
    node_type: str
    label: str
    params: dict


@dataclass
class ParsedGraph:
    nodes: dict[str, ParsedNode] = field(default_factory=dict)
    outgoing: dict[str, list[str]] = field(default_factory=dict)
    incoming: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ParseResult:
    graph: ParsedGraph
    issues: list[ValidationIssue]


def parse_graph(graph: StrategyGraph) -> ParseResult:
    issues: list[ValidationIssue] = []
    parsed = ParsedGraph()

    for node in graph.nodes:
        if node.id in parsed.nodes:
            issues.append(
                ValidationIssue(
                    node_id=node.id,
                    code="DUPLICATE_NODE_ID",
                    message=f"Duplicate node id '{node.id}'",
                    severity="error",
                )
            )
            continue

        node_type = node.data.node_type
        if node.type and node.type != node_type:
            issues.append(
                ValidationIssue(
                    node_id=node.id,
                    code="NODE_TYPE_MISMATCH",
                    message=(
                        f"Node 'type' ('{node.type}') does not match 'data.nodeType' "
                        f"('{node_type}') — treating '{node_type}' as authoritative"
                    ),
                    severity="warning",
                )
            )

        parsed.nodes[node.id] = ParsedNode(
            id=node.id, node_type=node_type, label=node.data.label, params=dict(node.data.params)
        )
        parsed.outgoing.setdefault(node.id, [])
        parsed.incoming.setdefault(node.id, [])

    # Named crossover ports keep operands stable when edges are reordered.
    # Legacy graphs without ports retain their existing edge order.
    edges = sorted(graph.edges, key=lambda edge: {"left": 0, "right": 1}.get(edge.target_handle, 0))
    for edge in edges:
        if edge.source == edge.target:
            issues.append(
                ValidationIssue(
                    node_id=edge.source,
                    code="SELF_LOOP",
                    message=f"Node '{edge.source}' has an edge to itself",
                    severity="error",
                )
            )
            continue
        if edge.source not in parsed.nodes:
            issues.append(
                ValidationIssue(
                    node_id=edge.source,
                    code="DANGLING_EDGE",
                    message=f"Edge references unknown source node '{edge.source}'",
                    severity="error",
                )
            )
            continue
        if edge.target not in parsed.nodes:
            issues.append(
                ValidationIssue(
                    node_id=edge.target,
                    code="DANGLING_EDGE",
                    message=f"Edge references unknown target node '{edge.target}'",
                    severity="error",
                )
            )
            continue

        parsed.outgoing[edge.source].append(edge.target)
        parsed.incoming[edge.target].append(edge.source)

    return ParseResult(graph=parsed, issues=issues)
