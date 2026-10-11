# Paper simulation

AlgoFlow paper trading runs locally in the API/background worker and never
calls an exchange order endpoint. No API keys are needed. Binance Futures Demo
is a separate exchange-hosted simulated execution service.

## Start and select an account

Save the graph in Strategy Builder first. In Paper Trading select the saved
strategy, Spot or USDT Futures, symbol (`BTC/USDT`), timeframe and starting
virtual balance. Futures also supports 1–10x leverage. The simulation assumptions
panel configures fees and slippage, and futures funding/maintenance ratios.

Each account pins its saved strategy version. Builder edits do not change a
running account. Start another account to use the newer version. The account
selector scopes balances, positions, fills and equity history to one account;
accounts and all controls require the owning user's JWT.

- Spot graphs use `buy` / `sell`; sells cannot create a short position.
- Futures graphs use `openLong` / `openShort` / `closePosition`. Only market
  entries, one isolated position and linear USDT contracts are supported.
  Position size is the action node's base-asset `amount`; insufficient margin
  rejects an entry rather than silently shrinking its quantity.
- Fee/slippage defaults are 0.1% / 0.05%, editable per new account. They are
  simulation inputs, not live account fee schedules.
- Sentiment is still unavailable to the paper strategy evaluator. A strategy
  dependent on it must not be interpreted as tested with validated sentiment.

## Worker and explanations

Run `docker compose up -d api paper_worker` from `backend/`. API startup runs
Alembic migrations. The worker scans active accounts and sleeps 15 seconds
between scans; exchange reads can extend the scan duration. `Check strategy now`
invokes the same runner and can create **local simulated** fills. Refresh and
15-second page polling only read status; they never trigger execution.

The runner evaluates newly closed candles, locks the account row before
mutations, and stores `last_processed_bar` transactionally. Repeated/concurrent
ticks cannot trade the same candle twice. A PostgreSQL row lock also serializes
pause/resume/flatten and fills. SQLite tests cover accounting and API behavior;
production locking relies on PostgreSQL.

The Why no trade panel records actual node values, conditions, signals, pinned
version, candle timing and the last decision/blocking error. Its worker timestamp
is distinct from lifecycle updates. A 90-second stale heartbeat is an operational
warning, not proof that exchange data or the worker is healthy. Failures are
recorded without inventing fills, neutral sentiment or market data.

Spot uses the existing public CCXT provider priority (Binance, Bybit, Kraken),
with the selected provider recorded. Futures uses public Binance USD-M contract
candles through CCXT `binanceusdm`, with **no fallback to spot candles**.
Missing/stale candles block execution. The runner checks up to 500 recent bars;
a larger unprocessed gap blocks and needs Stop & Close or a new account.

## Exits and lifecycle

Protective exits inspect each new candle's high/low for an existing position.
If both stop and target are touched, choose the adverse exit. Adverse opening
gaps execute at the opening price (plus configured slippage), not a guaranteed
stop price. A target fills at its threshold without favourable gap improvement.
Entry at candle close cannot use that same candle's earlier high/low to exit.
A protective exit prevents a fresh strategy entry on that candle.

Queued spot limits fill when a later candle touches the limit, use its opening
price if better, and never violate the limit after slippage. Saved protective
percentages attach on fill. For a limit fill and stop touched in the same candle,
assume the adverse stop follows the fill; OHLC cannot establish the actual order.
Volume, spread, market impact, latency and partial fills are not modeled.

Pause cancels pending orders and retains positions. The account's protection,
mark updates and funding stop running while paused; resume processes retained
history before evaluating the latest candle. Stop & Close can also flatten a
paused account, reads a fresh public price, settles futures funding through the
closing time, cancels pending orders and pauses in one transaction. If price
fetching fails, it does not report a successful close.

## Isolated futures assumptions

Opening subtracts `entry_notional / leverage + entry_fee` from free cash. The
position retains its isolated margin. Equity equals free cash + retained margin
+ signed unrealized P/L. Closing returns collateral plus P/L less exit fees;
realized trade P/L includes entry fees and accumulated signed funding.

Funding uses the **configured fixed scenario rate**, not fetched exchange rates,
at 00:00 / 08:00 / 16:00 UTC. Positive rates debit longs and credit shorts;
negative rates reverse this. Each boundary is applied once using candle-close
notional when the closed-bar runner processes it. Protective intrabar exits are
assumed to precede the candle-end funding settlement. Longer timeframes and
partial entry candles cannot reproduce exact event timing. The scenario is
clearly displayed in the account settings; use exchange Demo for fidelity.

Liquidation is a simplified fixed-maintenance model, using contract-price OHLC
as a proxy for mark price and reserving the closing fee. With quantity `q`, entry
`e`, retained margin `m`, and reserve `r = maintenance_rate + fee_rate`:

- Long threshold: `max(0, (e - m/q) / (1-r))`.
- Short threshold: `(e + m/q) / (1+r)`.

Crossing it removes the isolated collateral and closes the position. Free cash
outside that position is not spent; a price gap cannot create a negative account
balance. Funding changes retained margin and therefore the threshold. This does
not reproduce Binance mark-price triggers, tiered maintenance, ADL, insurance
funds, liquidation penalties or exchange rounding/minimum order rules. It is
suitable for local algorithm experiments, not evidence of real-money readiness.

Public API reference: [Binance USD-M market data](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data).

## API and history

`POST /api/paper-trading/start` accepts strategy_id, symbol, timeframe,
starting_balance, market_type, leverage, fee_rate, slippage_rate, funding_rate and
maintenance_margin_rate. Decimal rates use fractions: `0.001` means 0.1%.
Settings are immutable for the account. Legacy accounts migrate to spot defaults.

- `GET /accounts` lists only owned accounts.
- `GET /account`, `/positions`, `/trades`, `/performance` accept
  `paper_account_id` (required for positions/performance).
- `POST /tick`, `/resume`, `/stop` take `paper_account_id`.
- `/stop` additionally accepts `close_positions: true`.
- Manual `/orders` and `/simulate-fill` remain spot-only developer helpers; the
  latter accepts a user-supplied price and is not a market fidelity check.

Equity snapshots are written at creation, new-candle checks, lifecycle changes
and manual fills. The selected account chart uses actual snapshots, including
unrealized losses and fees. Historical snapshots are not backfilled for legacy
accounts. Win rate derives from closed fills; Sharpe remains unavailable rather
than invented. Existing global portfolio summaries aggregate owned accounts,
including futures collateral and signed P/L; different quote currencies should
be viewed separately because conversion is not modeled.

## Verification

`pytest` covers long/short cash flows, fees, signed funding idempotency, isolated
liquidation, OHLC ambiguity/gaps, spot flattening from pause, pending cancellation,
closed-candle idempotency, API ownership and account data separation, rejected
settings/margin, and persisted market-failure diagnostics. No exchange execution
is needed for these tests.
