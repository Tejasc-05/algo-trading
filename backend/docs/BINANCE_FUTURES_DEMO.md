# Binance Futures Demo

This release implements **Binance USD-M demo execution only**. No production hostname or production order adapter is accepted. `ENABLE_LIVE_TRADING` does not enable this adapter to trade real money. Delta is the next integration, not part of this release.

## Setup

1. Create a dedicated Binance Futures demo account and obtain **demo** API credentials. Do not reuse a production key, share it in chat, commit it or put it in a frontend environment variable.
2. In AlgoFlow's Live Trading page, save a sandbox connection using `binanceusdm` (or `binance`) as the exchange ID. Only active sandbox connections are offered in Binance Futures Demo.
3. Select that connection and click **Verify Demo Account**. This checks a signed account endpoint, one-way positions, single-asset mode and account trading availability. It does not prove the key has trade permission; a confirmed demo order verifies that separately.
4. Use a dedicated account with no existing positions, regular orders, conditional orders, manual trading or other bots. Separate API keys can belong to the same exchange account: do not run multiple keys against it.
5. Load **Futures MACD Long** or **Futures MACD Short**, review quantity and risk settings and save. Quantities use base-asset units, not quote currency or arbitrary contract counts. Legacy BUY/SELL graphs map to long entry/full close only.
6. Select your saved algorithm, BTCUSDT or ETHUSDT, timeframe, maximum position notional and maximum loss since activation. Confirm demo funds, then **Start Futures Demo**. Activation selects isolated margin and 1x leverage and pins the latest saved strategy version.
7. Use **View Demo Orders**, **Reconcile / Run Tick**, **Resume Demo** or **Stop & Close Demo**. Stop disables new entries, reconciles orders, submits a reduce-only market close and cancels protection only after the position is confirmed flat. Stop is not an unconditional guarantee during exchange/network outages; use Binance's interface to inspect and manage the account if reconciliation cannot complete.

The worker polls every 15 seconds and evaluates closed candles only. It fetches demo market data, not spot/paper fixtures. Changing the saved graph does not modify a running session. Stop and activate again to adopt edits.

## Supported scope

- BTC/ETH USDT perpetual contracts, one-way positions, single-asset USDT margin, isolated margin, 1x leverage.
- Explicit `openLong`, `openShort`, `closePosition` nodes, plus legacy long-only BUY/SELL graphs.
- Market actions only. Exactly one stop-loss and one take-profit node, each in (0,10]%, must fire alongside entry.
- Binance market quantity/minimum-notional filters and price tick rounding.
- Maximum configured notional 1,000 USDT; maximum loss since activation 100 USDT. These are software demo limits, not investment recommendations. Account equity includes exchange-reported unrealized P&L and funding/fees; this is a session loss threshold, not a calendar-day guarantee.
- Exchange-held mark-price STOP_MARKET/TAKE_PROFIT_MARKET protection, full-position close semantics.
- No pyramiding, hedge mode, cross margin, arbitrary leverage, futures limit actions, sentiment trading or futures funding/margin backtesting.

## Durable execution

`futures_demo_sessions` stores user ownership, a pinned strategy version, limits, status, last processed bar and a processing lease. One non-stopped session is allowed per saved connection. Leases expire after 15 minutes; after a crashed worker, processing may wait until lease expiry. Postgres uniqueness and conditional lease updates arbitrate concurrent worker/API ticks.

`futures_demo_orders` stores deterministic client IDs and submission intent before network writes. Market and conditional order outcomes are queried by those IDs after timeouts/restarts. Unknown outcomes are not automatically resubmitted. A stale, never-submitted market intent is abandoned. Known partial fills get protection and pause new entries until reconciliation. Protection failure attempts a reduce-only close, pauses the session and requires inspection. A response timeout during that close still requires reconciliation.

The worker processes `running` sessions. `paused`/`needs_attention` sessions require manual reconciliation/resume. Resume does not reset the loss baseline or ignore unresolved orders. Disconnect is blocked for non-stopped demo sessions; when stopped history exists, disconnect erases credentials while retaining the audit reference.

## API

- `POST /api/futures-demo/connections/{id}/verify`
- `POST /api/futures-demo/sessions` (requires `confirm_demo: true`)
- `GET /api/futures-demo/sessions`
- `POST /api/futures-demo/sessions/{id}/tick`
- `POST /api/futures-demo/sessions/{id}/stop`
- `POST /api/futures-demo/sessions/{id}/resume`
- `GET /api/futures-demo/sessions/{id}/orders`

All private endpoints are user-scoped. Keys are decrypted only in the transport and never returned. HTTP client debug logs are suppressed so signed request URLs are not logged. User-facing exchange failures omit raw response bodies and credentials.

Verification reads balances from `/fapi/v3/account` and trading availability from `/fapi/v1/accountConfig`. V3 does not expose `canTrade`; an omitted flag must not be interpreted as a disabled account. An explicit configuration `canTrade: false` blocks activation, while a missing or malformed configuration flag reports unknown status and also blocks activation.

## Run and verify

From `backend/`, run migrations and rebuild/start the API plus workers:

```sh
alembic upgrade head
docker compose up -d --build api paper_worker futures_demo_worker
```

For local execution without Docker, start `python -m app.futures.worker` alongside FastAPI after migrating. Tests run from the repository checkout; template JSON is shared with frontend tests.

Automated tests cover signing/host restrictions, ownership, pinned graph interpretation, entry/short/close mapping, exchange-held protection, duplicate ticks, durable timeout recovery, partial fills, failed protection, loss limits, notional limits and processing leases. Browser checks use a real local user/strategy save, with controlled responses for demo Start/Stop UI. Public Binance demo time and BTC/ETH market metadata were reachable. **Authenticated demo balances/orders remain unverified until genuine demo credentials are entered.** No real-money or credentialed demo order was submitted during implementation.

Real-money rollout still requires authenticated demo acceptance tests, longer-running disconnect/restart/market-event tests, account eligibility checks, a reviewed production adapter, protection/reconciliation acceptance checks and operational deployment hardening. Passing these software checks does not validate strategy profitability.

## Official references

- [Binance USD-M general information and demo host](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info)
- [Order, conditional-order and reconciliation API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade)
- [Account and position API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account)

## Why no trade? diagnostics

Migration `0007_futures_diagnostics` adds a nullable JSON snapshot to each demo
session. The existing user-scoped session responses include it; viewing or
refreshing this data performs no exchange requests and cannot submit orders.
The runner records a heartbeat, observed position, decision/blocking code and
safe error message. Last candle evaluation is retained separately, including
open/close times, next expected candle close, pinned strategy version, candle
count/close, node outputs and entry/exit signals. MACD reports the configured
periods and line/signal/histogram values for current and previous closed candles.
Comparison/crossover/logic inputs and results come from the same engine evaluation
that produced signals, rather than a second diagnostic evaluation. Missing or
nonfinite warm-up values are serialized as null, not NaN or zero.

The UI flags running-session snapshots older than 90 seconds. This is a display
policy, not proof of worker failure. Duplicate candle checks update only the
heartbeat/reconciliation context and retain the last evaluation; they do not
re-evaluate or submit additional entries. Legacy sessions can show no evaluation
until the next *new* closed candle is processed. Stop/resume and errors update the
reason without claiming the previous indicator values were recomputed.

Entry-limit diagnostics show observed mark price, rounded quantity, minimum
notional, session cap and available margin (including the existing 5% buffer
check). These are populated only when the runner reaches that check, and cleared
on a new evaluation. Checks are observations, not authorization to force a trade.
The last blocking error is retained until an evaluation or successful resume clears
it. Confirm actual exchange exposure using reconciliation when order outcomes are
unknown. Snapshot values are historical observations and not a live position feed.

After applying migrations, rebuild/restart the API and futures demo worker so both
can write/read snapshots. Avoid interrupting an active processing lease; if a
worker crashes mid-tick, the existing lease expiry/reconciliation rules still apply.
No additional API credentials are needed. Production execution stays disabled.
