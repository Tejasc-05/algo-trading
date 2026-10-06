import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.schemas.strategy import StrategyGraph
from app.strategy_engine.executor import StrategyExecutor
from app.strategy_engine.validator import validate_strategy_graph

TEMPLATES = json.loads((Path(__file__).resolve().parents[2] / 'src/features/strategy-builder/templates.json').read_text())


def context(values):
    return {'candles': pd.DataFrame({'close': values})}


@pytest.mark.parametrize('template', TEMPLATES, ids=lambda t: t['id'])
def test_templates_validate_warm_up_and_generate_entries_exits(template):
    graph = StrategyGraph.model_validate(template['graph'])
    assert validate_strategy_graph(graph).valid
    executor = StrategyExecutor(graph)
    assert executor.evaluate(context([100.] * 5)) == []
    values = np.concatenate([np.linspace(150, 80, 100), np.linspace(80, 200, 100), np.linspace(200, 50, 100)])
    actions = set()
    for end in range(6, len(values) + 1):
        actions.update(signal.action for signal in executor.evaluate(context(values[:end])))
    assert {'buy', 'sell', 'set_stop_loss', 'set_take_profit'} <= actions


def test_crossover_ports_survive_edge_reordering():
    graph = StrategyGraph.model_validate(TEMPLATES[0]['graph'])
    reverse = graph.model_copy(update={'edges': list(reversed(graph.edges))})
    values = np.concatenate([np.linspace(150, 80, 100), np.linspace(80, 200, 100)])
    first, second = StrategyExecutor(graph), StrategyExecutor(reverse)
    for end in range(50, len(values) + 1):
        a = {(s.node_id, s.action) for s in first.evaluate(context(values[:end]))}
        b = {(s.node_id, s.action) for s in second.evaluate(context(values[:end]))}
        assert a == b
    graph.edges[1].target_handle = 'left'
    assert not validate_strategy_graph(graph).valid


@pytest.mark.asyncio
async def test_template_save_updates_latest_execution(client, auth_headers):
    template = TEMPLATES[1]
    result = await client.post('/api/strategies', headers=auth_headers,
                              json={'name': template['name'], 'graph': template['graph']})
    assert result.status_code == 201
    strategy_id = result.json()['id']
    graph = json.loads(json.dumps(template['graph']))
    graph['nodes'][1]['data']['params']['value'] = 100
    graph['nodes'][3]['data']['params']['amount'] = 0.002
    result = await client.put(f'/api/strategies/{strategy_id}', headers=auth_headers,
                             json={'name': 'Edited RSI', 'graph': graph})
    assert result.status_code == 200
    assert result.json()['current_version'] == 2
    result = await client.post(f'/api/strategies/{strategy_id}/execute', headers=auth_headers)
    assert result.status_code == 200
    buys = [signal for signal in result.json()['signals'] if signal['action'] == 'buy']
    assert buys and buys[0]['params']['amount'] == 0.002
