# Existing React integration

The React frontend is retained. The builder uses `@xyflow/react` and Zustand.
Its current palette has `rsi`, `macd`, `movingAverage`, `condition`, `sentiment`,
`buy`, `sell`, `stopLoss`, and `takeProfit`. The backend also accepts price,
volume, SMA, EMA, Bollinger Bands, AND, OR, NOT, and HOLD.

Graphs use this exact wire format:

```json
{
  "name": "RSI Oversold Strategy",
  "graph": {
    "nodes": [
      {"id":"rsi-1","type":"rsi","position":{"x":100,"y":150},"data":{"label":"RSI","nodeType":"rsi","params":{"period":14}}},
      {"id":"condition-1","type":"condition","position":{"x":350,"y":150},"data":{"label":"Condition","nodeType":"condition","params":{"operator":"<","value":30}}},
      {"id":"buy-1","type":"buy","position":{"x":600,"y":100},"data":{"label":"Buy","nodeType":"buy","params":{"amount":0.1,"type":"market"}}}
    ],
    "edges": [
      {"id":"e1","source":"rsi-1","target":"condition-1","sourceHandle":"source","targetHandle":"target"},
      {"id":"e2","source":"condition-1","target":"buy-1","sourceHandle":"source","targetHandle":"target"}
    ]
  }
}
```

`data.nodeType` is authoritative. Params are validated and normalized against
the allowlisted registry. Position and edge handles survive saves. Draft graphs
can be saved before semantic validation; invalid graphs cannot execute or start
paper accounts. Actions, logic and risk nodes require boolean gates. Unknown
indicator warm-up values remain unknown through NOT, rather than becoming trades.
There is no user code generation or dynamic Python execution. Limits: 256 nodes,
1024 edges, and 10000 candles per backtest request.

## REST

Access the complete typed request/response contract at `/docs` or `/openapi.json`.
Private REST routes require `Authorization: Bearer <access_token>`.

| Area | Routes |
|---|---|
| Auth | POST `/api/auth/register`, POST `/api/auth/login`, GET `/api/users/me`, GET `/api/auth/me` |
| Strategies | POST/GET `/api/strategies`, GET/PUT/DELETE `/api/strategies/{id}`, POST `/{id}/validate`, POST `/{id}/execute` |
| Market | GET `/api/market/ticker?symbol=BTC/USDT`, GET `/api/market/ohlcv?symbol=BTC/USDT&timeframe=1h&limit=100` |
| Backtest | POST `/api/backtest`, GET `/api/backtest/{id}` |
| Paper | POST `/api/paper-trading/start`, `/stop`, `/tick`, `/orders`, `/simulate-fill`; GET `/account`, `/trades` |
| Portfolio | GET `/api/portfolio`, `/api/portfolio/performance` |
| Exchanges | POST `/api/exchanges/connect`, GET `/api/exchanges`, DELETE `/api/exchanges/{id}`, POST `/{id}/test` |
| Sentiment | GET `/api/sentiment/{symbol}` |

Creation of strategies returns 201. Version updates create immutable snapshots.
Ownership failures use 404 to avoid revealing another user's resources.
Errors use `{"success":false,"error":{"code":"...","message":"..."}}`.

Start paper trading with a saved strategy:

```json
{"strategy_id":"<saved-id>","symbol":"BTC/USDT","timeframe":"1h","starting_balance":10000}
```

Paper accounts pin a strategy version. Start a new account to adopt a new version; Resume retains the pinned version.
`/simulate-fill` accepts an explicit test price and is a development simulation
tool, not an authoritative market price source. It updates balances, positions
and trades atomically, rejects duplicate settlement, and never sends real orders.
Spot paper mode requires holdings for sells and cash including fees for buys.
USDT futures paper mode supports explicit Open Long/Short/Close Position actions,
isolated margin, configurable funding scenarios and approximate liquidation.
See [PAPER_TRADING.md](PAPER_TRADING.md) for settings, limitations and API controls.
Spot limit orders stay pending until their limit is reached. The worker settles
pending orders and evaluates only closed candles. PostgreSQL row locks and
persisted timestamps serialize repeated ticks; SQLite unit tests do not validate
PostgreSQL's concurrency behavior.

## Frontend data corrections

Authenticated pages no longer import the mock-data module. Paper Trading reads
the account, trades, positions and performance endpoints. Dashboard and Portfolio
read the actual flat API fields. Live Trading lists stored exchange connections;
it does not invent bots or live profit. Sentiment reports unavailable until a real
provider is configured. Notifications start empty. Settings no longer claims a
paid subscription or billing date. Landing-page illustrative content is retained.

The paper page provides account-scoped setup, Pause/Resume, Stop & Close,
equity history and worker/algorithm diagnostics using saved strategies. Layout,
styling and graph structures are retained. Errors and empty states are visible.
The API client clears expired sessions; protected pages redirect to login.

## WebSocket

Connect to `/ws` with subprotocols `['algoflow', accessToken]`. Tokens stay out of
URLs. Browser origins must match `CORS_ORIGINS`. The backend authenticates the JWT
and active user and subscribes to the private Redis channel `user:<user-id>`.

```json
{"event":"paper_order","data":{"order_id":"...","symbol":"BTC/USDT","executed_price":100.05,"executed_quantity":1,"fee":0.10005,"pnl":null}}
```

The worker publishes `paper_order` and `portfolio_update` after committed fills.
The frontend reconnects with backoff and refreshes API data on events and focus.
Redis pub/sub is transient; REST/database reads recover missed events. Price and
candle publishers are available for future subscriptions; a shared public-market
subscription UI is not yet implemented. Socket token refresh during long sessions
is a remaining task.

## Simulation conventions and limits

VectorBT runs its actual portfolio engine over the safe graph simulator's fill
plan and checks the final cash/holdings reconciliation. Signal generation remains
bar-by-bar and is not yet optimized for large parameter sweeps. Close-derived
signals execute at the next candle open. Risk exits use candle high/low; stop loss
wins when both levels could hit in one candle. Gap stops use the worse open price.
Entry and exit fees count in realized P/L, and final liquidation updates equity.
VectorBT adapter supports market orders and risk nodes; limit backtests are rejected.

Backtrader runs an independent event-driven market-only spot graph adapter,
including next-bar order execution. It currently rejects risk nodes and limits,
and values remaining holdings at the final mark rather than forcing liquidation.
Different fill conventions mean engines need not give identical results.

Trade counts and win rates count closed trades, not opening fills. Sharpe is
per-bar, not annualized. Portfolio historical charts show realized-profit history;
historical mark-to-market snapshots and monthly returns are not yet implemented.
Current portfolio equity includes last observed position marks. No generated
prices are returned when exchanges fail; market APIs return 503. Public market
data uses an explicit fallback exchange order and may consequently come from
different venues. Historical data source/provenance persistence remains future work.

Sentiment has a swappable provider interface. Unimplemented news providers return
503; no fabricated score is exposed and no model is trained. Real execution is
unavailable even if `ENABLE_LIVE_TRADING=true`: order-risk limits, exchange
confirmation, idempotency and reconciliation must be implemented and reviewed
before live execution is added. Backtests do not establish future profitability.

Library API references: [VectorBT](https://vectorbt.dev/api/portfolio/base/),
[Backtrader](https://www.backtrader.com/docu/strategy/).
