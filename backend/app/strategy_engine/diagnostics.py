"""Small JSON-safe snapshots of actual node outputs; no candle arrays or execution."""
import math
import numpy as np
import pandas as pd
from app.strategy_engine.nodes.base import NodeCategory


def scalar(value):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.number)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def tail(value):
    if isinstance(value, dict):
        return {key: tail(item) for key, item in value.items()}
    if isinstance(value, (np.ndarray, pd.Series, list, tuple)):
        values = list(value[-2:])
        return {'current': scalar(values[-1]) if values else None,
            'previous': scalar(values[-2]) if len(values)>1 else None}
    return {'current': scalar(value), 'previous': None}


def node_snapshot(node, definition, inputs, output, details=None):
    terminal = definition.category in {NodeCategory.ACTION, NodeCategory.RISK}
    item = {'id': node.id, 'label': node.label, 'node_type': node.node_type,
        'category': definition.category.value, 'params': dict(node.params),
        'inputs': [tail(value) for value in inputs]}
    if terminal:
        item['triggered'] = output is not None
    else:
        item.update(tail(output))
    if details:
        item['macd'] = details
    return item
