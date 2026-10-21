"""History needed for indicator warm-up, a crossover pair and an open bar."""


def candle_limit(graph, minimum=100):
    required = minimum
    for node in graph.nodes:
        kind, params = node.data.node_type, node.data.params
        if kind == 'macd':
            warmup = int(params.get('slow', 26)) + int(params.get('signal', 9)) - 1
        elif kind == 'rsi':
            warmup = int(params.get('period', 14)) + 1
        elif kind in {'movingAverage', 'sma', 'ema', 'bollinger_bands'}:
            warmup = int(params.get('period', 50 if kind == 'movingAverage' else 20))
        else:
            continue
        required = max(required, warmup + 2)
    return required
