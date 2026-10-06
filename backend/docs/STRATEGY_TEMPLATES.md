# Strategy templates and builder inputs

The existing builder offers three editable starting graphs. They are drafts until saved; loading a template never starts a bot. Paper trading is started separately from Paper Trading. Real execution remains disabled.

| Template | Entry | Exit |
| --- | --- | --- |
| EMA Trend Crossover | EMA(20) crosses above EMA(50) | EMA(20) crosses below EMA(50) |
| RSI Mean Reversion | RSI(14) < 30 | RSI(14) > 70 |
| MACD Momentum | MACD(12,26,9) histogram > 0 | Histogram < 0 |

MACD uses momentum state, not a crossover event. EMA crossover ports A/left and B/right explicitly define operand order; legacy graphs without named ports preserve edge order. Keep both A and B connected when using crossover operators. Comparison operators use one numeric input and a literal compare value. RSI thresholds belong on the condition nodes, while the RSI period controls the indicator itself.

Each template has example quantities of 0.001 base asset units, 2% stop loss and 5% take profit. These are editable examples, not optimized parameters. Quantity must be affordable for the chosen symbol/account; selling is limited to existing spot holdings. The entry condition gates buy, stop loss and take profit together. Templates must be assessed with realistic fees, slippage, unseen periods and buy-and-hold comparisons before use. No performance claims or profitability ranking are included.

Node parameters use fixed numeric input types and dropdowns for enumerations. Blank values, invalid periods, invalid fast/slow ordering, nonpositive quantities and risk percentages outside (0,100] are blocked before saving. A limit order requires a positive limit price. Backend validation is still authoritative. Save updates the existing strategy; Test Run first persists the current graph as its latest version, validates it, then evaluates the latest closed BTC/USDT 1h candle. It produces signals, not orders. Loading a template starts a new draft and asks before replacing unsaved work.

Template definitions live in `src/features/strategy-builder/templates.json`. Backend tests load the same definitions, validate them, exercise warm-up and entry/exit signals, and verify crossover port order and latest-version execution. Run tests from the repository checkout (the frontend JSON must be available).

The sidebar's authenticated `/api/paper-trading/usage` endpoint counts active paper accounts owned by the user and attached to strategies. A fresh account returns zero. There is no invented subscription cap or progress bar. Starting/stopping paper trading refreshes the count; network failures display unavailable.

## Research context

- [AQR: Time Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum): evidence for the broader trend-following family, not a validation of this particular EMA crypto implementation.
- [Fidelity: RSI](https://www.fidelity.com/viewpoints/active-investor/how-to-use-rsi): applicability and limitations of RSI in non-trending markets.
- [Fidelity: MACD](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd): line/signal relationship and momentum interpretation.

## User-owned persistence

Save stores the graph in PostgreSQL under the authenticated user's ID. The database is shared, but each user's strategy records are private: listing filters by owner, and reading, updating, deleting, validating or executing another user's strategy returns 404. Clients cannot assign ownership through the save payload.

Use **My Saved Strategies → Open Strategy** to reopen the latest saved graph after a reload. Further saves create versions of the same strategy, including after navigating away and back. Loading a prebuilt template starts a separate draft. Login, signup and logout reset the in-memory builder so a previous account's graph does not carry into the next session. Layout measurements and node selection do not mark a graph as edited.

## Integration verification and current limits

The builder validates the complete unsaved graph with `/api/strategies/validate-graph` before Save/Test Run. Tests verify edited period, threshold, quantity, risk values, positions and edge handles survive saving and feed actual execution. Saving changes persists graph JSON that the allowlisted engine evaluates; it does not generate Python code. Changes only become persistent after Save or Test Run.

An active paper account pins a strategy version. Save does not alter a running account; stop and start it to use the latest version. Test Run uses BTC/USDT, 1h and closed candles. Paper trading currently uses spot holdings and candle-close risk checks; it does not promise an intrabar stop-loss fill.

Exchange credentials are encrypted and user-scoped. The current connection test checks public market-data reachability and explicitly returns `credentials_verified: false`. Authenticated balance/permission verification and a real execution service with risk limits, reconciliation and exchange-specific order handling are still required. The live feature flag alone cannot enable real orders. Passing software tests is not evidence of strategy profitability.
