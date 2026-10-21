# AlgoFlow project audit — 21 October 2026

Follow-up: [multi-user release preparation](MULTI_USER_RELEASE.md) records subsequent cookie-session, verification/MFA and PostgreSQL integration work. Its current status supersedes the localStorage and untested-PostgreSQL statements below; genuine exchange and public deployment acceptance remain outstanding.

This review covers the current working tree, including the previously uncommitted password reset and sentiment work. It is a code review and functional/security regression audit, not a certification of profitability or readiness to trade real money. No authenticated exchange orders were submitted and no user account was changed.

## Confirmed defects corrected

| Area | Finding | Correction and evidence |
| --- | --- | --- |
| Strategy conditions | A crossover returned false while an indicator was warming up; NOT could turn that into an entry. Missing crossover inputs could also raise an exception. | Preserve unknown values until two finite observations exist; missing inputs produce no trigger. Regression tests cover both crossover directions and NOT. |
| Paper execution | Multiple simultaneous actions selected whichever appeared first in graph traversal. Multiple protective levels also depended on ordering. | Skip ambiguous strategy orders, preserve existing protection, and report `CONFLICTING_SIGNALS`. Explicit futures closes can still reduce exposure. Spot and futures regression tests assert no orders are created. |
| Candle continuity | The first missing bar immediately after the processed bar was not detected if older history was still present. | Check that the first unprocessed bar is exactly the next expected bar, as well as checking gaps inside the new range. |
| Indicator history | Builder Test Run fetched only 100 bars and paper execution 500; valid larger indicator settings could never warm up. | Request enough history for the longest indicator, two observations and the unfinished exchange candle. Tests evaluate maximum-period SMA, RSI and MACD with actual indicator functions. |
| Market data | Impossible OHLC ranges were accepted. | Reject highs/lows that do not contain the candle's open and close. |
| Backtests | Reference simulator sold the entire position regardless of the sell node quantity, omitted slippage on final liquidation, and could miss risk nodes visited before an entry. | Respect partial quantities, allocate entry fees proportionally, apply final-exit slippage, and apply triggered risk nodes after actions. Conflicting actions are skipped in both adapters. |
| Demo protection | A failed status query left an old `NEW` protection state usable. Completed or unrecognized protective states could also be accepted as active. | Failed reconciliation becomes `UNKNOWN` and blocks further entry. Only confirmed `NEW` protection is accepted. Protection failure attempts a reduce-only flatten; recovery reloads the full protective ledger before cleanup. Unknown submissions are never blindly retried. |
| Demo account mode | Missing one-way/single-asset fields passed verification. | Require explicit boolean false for both alternative modes. |
| Strategy deletion | Deleting a pinned paper strategy orphaned its account; demo/backtest references could produce a server error. | Retain strategies with paper/demo/backtest history and return a clear 409. Existing pinned algorithms remain available. |
| Registration | Two concurrent requests for the same email could produce an unhandled unique-constraint error. | Translate the database conflict to the existing `EMAIL_TAKEN` response after rollback. |
| API privacy | Private API responses lacked explicit cache prevention; oversized bearer tokens reached JWT parsing. | API responses use `Cache-Control: no-store` and `nosniff`; reject tokens larger than 8 KiB. Nonfinite canvas coordinates are rejected before persistence. |
| Simulation helper | Caller-supplied prices were available in any deployment environment. | `/paper-trading/simulate-fill` is development-only. Normal worker fills continue to use public market data. |
| Local infrastructure | Postgres and unauthenticated Redis ports bound all host interfaces. | Compose publishes them on `127.0.0.1` only. This change takes effect when containers are recreated. |
| Dependencies | Frontend and Python packages had known advisories, including the optional sentiment runtime. | Updated the npm lockfile, CCXT/HTTP dependencies, JWT/crypto/multipart, test tools, Pillow, Torch and Transformers. Exact versions are in the requirements files; dependency resolution and real FinBERT loading were checked. |
| Build configuration | Vite warned that `__dirname` would break its future native config loader. | Resolve the source alias through `import.meta.url`. |

## Verification

- **240 backend tests pass**, with no test warnings in the final run.
- Backend tests exercise authentication and reset-token revocation, private-route authentication, ownership isolation, graph validation/execution, spot/futures paper accounting, pending limits, protective exits, funding/liquidation scenarios, demo reconciliation and loss limits, backtest adapters, RSS parsing, sentiment review isolation and WebSocket revocation.
- The audit adds a private-route authentication matrix and tests proving one paper account failure does not stop the worker processing another account, and paused accounts/sessions are not run.
- Full suite runs in a clean Python 3.12 environment under `work/audit-venv`, including actual VectorBT and Backtrader. Core API tests use SQLite, fake Redis and injected market/exchange responses.
- Combined backend statement/branch coverage is approximately 71%, not 100%. Coverage artifacts are in `work/audit-coverage.json` and `work/audit-coverage.txt`.
- Frontend TypeScript/production build passes. Lint has warnings, principally React hook dependencies/purity and Fast Refresh exports; it has no lint errors. The large JS bundle remains a performance warning.
- Browser checks use isolated fixture accounts/responses: password recovery, removal of social-login options, saving/renaming algorithms, keyboard/mobile search, and fresh/older news handling. They do not constitute an end-to-end test against the user's running database.
- Dashboard, paper trading, live trading, portfolio, settings and strategy builder also passed render smoke checks at desktop and mobile widths (12 page/viewport combinations), with no uncaught page exceptions. These checks use empty-account API fixtures and do not verify every control or live WebSocket connectivity.
- `npm audit` and `pip-audit` of the complete updated local Python environment, including the optional sentiment dependencies, report no known vulnerabilities at audit time. This does not prove absence of exploitable application bugs. Core dependency scans are now included in GitHub CI.
- Real public Binance spot OHLCV retrieval succeeded after the CCXT upgrade. Real RSS collection plus local inference returned 30 BTC headlines, with 21 fresh headlines from three publishers at the time of the check.
- The exact pinned FinBERT revision loaded using Torch 2.13.0 and Transformers 5.10.4 and returned finite, normalized class probabilities. This verifies runtime compatibility, not model accuracy; an apparently neutral example was classified positive. Trading sentiment still needs a held-out benchmark.
- Compose configuration validation and PostgreSQL Alembic offline SQL generation through `0009_password_reset` pass. Docker was stopped: migrations were not applied to live Postgres, and database row-lock concurrency was not exercised.
- Secret-pattern checks found no matching private keys/provider-token patterns in the scanned source, and no actual `.env` or database file is tracked. This was not a full repository-history secret scan.

## Remaining limitations / next acceptance work

1. **Real-money execution is still unavailable.** The live adapter refuses orders even when its feature flag is enabled. Delta has no execution adapter. Keep that behavior until there is a separate reviewed implementation and exchange acceptance testing.
2. **Demo operational recovery needs live acceptance.** HTTP ambiguity, partial fills and protection failures have simulated tests. A `needs_attention` session stops automated entry processing and requires reconciliation; do not interpret this as continuous account-wide protection during an exchange/network outage. No genuine Binance demo order lifecycle was exercised here.
3. **Concurrency and deployment remain unverified.** Run concurrent PostgreSQL settlement/version/reset tests, worker restart tests and backup/restore tests on a disposable deployment. SQLite cannot prove `FOR UPDATE` behavior. Rebuild services to use the patched dependencies; running environments do not update automatically.
4. **Production hardening remains separate work.** Add deployment-level HTTPS, request/body/concurrency limits, abuse controls for expensive backtests/inference, monitoring, key rotation and recovery processes. Browser bearer tokens remain in localStorage, so script injection would expose them. MFA and verified-email signup are not implemented. Compose is a development deployment, not a hardened public service.
5. **Email delivery still needs configured SMTP.** Token expiry/reuse/revocation are covered; actual inbox delivery was not checked. Background email tasks are not a durable queue. See `PASSWORD_RESET.md`.
6. **Backtest assumptions differ by adapter.** VectorBT replays the reference fill plan and forcibly closes remaining exposure at the end. Backtrader marks remaining holdings to market and has different broker fill rules; it rejects risk-node/limit graphs. Futures backtesting is explicitly unavailable. Results should not be presented as interchangeable or as a profitability guarantee. Sharpe is currently per-bar, not annualized.
7. **Portfolio aggregation is limited.** Cross-account totals assume comparable quote currencies without FX conversion. Aggregate historical curves use realized P&L; account-specific curves use snapshots. Daily/weekly P&L cards are realized values, not full marked-equity changes. Use USDT accounts for comparable totals until currency-aware reporting is added.
8. **Some UI functions are intentionally unavailable.** Profile editing, notification preferences, billing and 2FA are disabled. Settings' direct password-change control is disabled; the email recovery flow is implemented. Public price-stream helpers are scaffolding, not an active market-wide WebSocket feed. Paper account events use the user-specific channel.
9. **Coverage gaps remain.** Local inference and public feeds were manually smoke-tested, but SMTP, Redis disconnect behavior, external transport errors and background service lifecycle paths are not exhaustively covered. Browser checks use fixtures, not a running full stack.

## Reproducing checks

From `backend/`, in a fresh Python 3.12 virtual environment:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-quant.txt coverage pip-audit
python -m coverage run --branch --source=app -m pytest -q
python -m coverage report
python -m pip check
python -m pip_audit --local
python -m alembic upgrade head --sql
```

Install the optional local sentiment dependencies and Torch using the instructions in `SENTIMENT.md` before scanning or exercising that runtime. Never use production exchange credentials in tests. The tests inject market data and exchange writes; the public-data smoke checks only read public endpoints.

From the repository root:

```sh
npm ci
npm run build
npm run lint
npm audit
```

Review criteria used the [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html), [Binance futures trade API documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade), and upstream [PyJWT](https://github.com/jpadilla/pyjwt/security/advisories) / [cryptography](https://github.com/pyca/cryptography/security/advisories) advisories alongside the package-manager audit databases.
