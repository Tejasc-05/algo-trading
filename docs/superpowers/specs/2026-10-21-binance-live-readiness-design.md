# Binance futures real-money release design

Status: multi-user scope requested by the user; implementation and release acceptance are not complete.

## Intent and scope

The user wants AlgoFlow ready for real-money trading, prioritizing Binance futures and Delta later. Preserve the React/React Flow frontend and the FastAPI modular monolith. Saved, owner-scoped, immutable algorithm versions remain the source of execution. Do not claim strategy profitability or enable production orders as part of a code change.

First release supports multiple users connecting their own dedicated Binance USDⓈ-M futures accounts; BTCUSDT and ETHUSDT perpetuals, one active strategy and one position per exchange account, one-way/single-asset mode, isolated margin, 1x leverage, market entries, exchange-hosted stop-loss and take-profit. Each exchange account belongs to one verified AlgoFlow user. Delta execution follows separately.

The user confirmed other users must be supported. Country of residence, Binance futures eligibility, deployment host/domain and numerical capital/loss limits are release inputs, not assumptions. They do not need to be supplied as secrets in chat. Limits have no enabled default and must be explicitly configured before activation.

User update: target users are mainly in India; no deployment server is available yet. This does not establish derivatives eligibility or permission to operate the service. Keep the India launch blocked until account/product eligibility and the platform's obligations are reviewed. A stable outbound IP and a public HTTPS domain must be provisioned before production API-key use. No hosting purchase or deployment is authorized by this document.

## Current evidence

- `app/exchanges/ccxt_service.py` blocks all real orders even with its feature flag enabled. Keep its generic order method blocked; live execution must pass through a dedicated orchestrator.
- `app/futures/binance_demo.py` pins requests to the demo host. Never repoint a demo connection to production.
- Demo sessions have persisted intent, deterministic client IDs, per-session leases, risk orders and reconciliation. These are foundations, not sufficient evidence for production readiness.
- Demo workers only poll `running` sessions; `needs_attention` stops automated reconciliation. Live monitoring must continue for all unresolved orders or exposure regardless of entry state.
- Current uniqueness is per connection row. Two saved keys for one exchange account could bypass it. Live activation needs verified exchange-account identity and account-level serialization.
- Auth uses bearer tokens in localStorage, and deployment currently uses a development Compose file. Both need hardening before a public live service.
- Prior audit: 240 backend tests passed with roughly 71% combined statement/branch coverage, fixture browser checks passed. No genuine demo order lifecycle or PostgreSQL concurrency acceptance was performed.

## Execution boundaries

1. Use an explicit immutable execution environment on live connections/sessions and a distinct live API namespace, tables and worker entry point. No request field may supply an exchange URL. Separate demo and production host allowlists, credentials, client-ID prefixes and response labels; test that either credential environment is rejected by the other transport.
2. Live records include owner, verified exchange-account identity, connection, pinned strategy version/hash, symbol, timeframe, policy snapshot, state, last evaluated candle and audit timestamps. Orders persist intent before submission, exchange/client IDs, state, cumulative fill quantities, fees and reconciliation evidence. Use Decimal for financial calculations.
3. Prevent simultaneous execution across duplicate connections with account-level PostgreSQL coordination and uniqueness constraints. Use a dedicated advisory-lock connection for each bounded account operation; abort on lock-connection loss. Commit intent through separate transactional sessions before network writes. Never claim exactly-once exchange execution: crashes and lost responses require reconciliation, not a second submit.
4. Unknown submissions block new entries. Query by persisted client ID and reconcile actual positions/fills; not-found alone never authorizes resubmission. Partial fills immediately enter protection/recovery handling. Unexpected or malformed exchange responses fail closed.
5. Keep account observation separate from permission to enter. A disabled entry flag, paused session, revoked login or worker restart must not silently stop reconciliation of open exposure. On recovery, establish authoritative exchange state before evaluating another candle.
6. Validate current symbol filters, tick/quantity sizes, available margin, isolated mode, leverage, current mark/quote freshness and closed-candle continuity. Reject conflicting action graphs, nonfinite data, unsupported nodes and missing stop/target paths. Sentiment remains dashboard-only until separately validated.
7. Enforce explicit per-trade notional, total exposure, trade-frequency and loss limits. Define daily loss from UTC start-of-day account equity adjusted for deposits/withdrawals, including realized/unrealized P&L, fees and funding. If transfers or equity cannot be reconciled, block entries. Retain session loss limits across restart; resetting a session must not reset account daily loss. User chooses monetary limits at activation under stricter operator caps.
8. Validate anticipated stop distance and funding/margin buffer before submission. Confirm exchange-hosted protection against actual filled exposure. Market entry and protection are not atomic: measure and alert on the unprotected interval; failed protection triggers a bounded reduce-only recovery close. If the close outcome is unknown, preserve existing protection and reconcile rather than retrying blindly. Do not promise losses cannot exceed configured limits.
9. Distinguish **Pause new entries** from **Stop and close**. The latter cancels pending entries, reconciles fills, sends only reduce-only closes and declares stopped only after exchange-confirmed flatness and protective-order cleanup. A global entry kill switch must preserve the recovery path. No automatic cancel-all timer that could remove stop orders while exposure remains.
10. Use authenticated user-data updates plus periodic REST reconciliation and reconnect snapshots. Rate-limit centrally by account/IP budget; persist retry/backoff state for reads. Never automatically retry an ambiguous write. External positions/orders or account-mode changes pause entries and alert; never silently adopt or liquidate an unrelated position. A separate explicit emergency action must describe its account-wide effect.

Two implementation policies resolved by the design review (engineering choices): a confirmed daily/session loss or exposure-limit breach disables entries and initiates reduce-only closing of confirmed managed exposure, then requires explicit reactivation after the blocker is resolved. Unknown ownership/state instead enters reconciliation and alerting while retaining protection; it must not liquidate unrelated exposure. **Pause new entries** continues strategy-generated exits, protection monitoring and reconciliation. A faulty strategy evaluator cannot prevent the independent risk/recovery loop from running.

## Account security and frontend

- Preserve existing screens; add a visibly separate production connection form, read-only verification result, readiness blockers and activation review. Saved credentials alone do not mean verified or active.
- Verify actual signed account access, account identity and API permissions. Require trading access, disabled withdrawal access and a fixed-IP restriction. Where an API cannot prove a restriction, display it as unverified and keep activation blocked pending an auditable operator check; never infer permission from a public ticker response.
- Keep secrets encrypted and absent from logs/API responses. Add a key rotation and revocation procedure. A revoked exchange key is an incident, not evidence that exposure is flat.
- Use secure HttpOnly same-origin browser sessions with CSRF/Origin protection, explicit expiry/revocation and WebSocket origin checks. Remove persistent browser bearer tokens. Require MFA and recent step-up authentication for adding production credentials, activation, policy increases and recovery settings. Recovery must not bypass MFA silently.
- Public signup requires verified email before live access, abuse controls, user-isolation acceptance and jurisdiction/product eligibility review. Paper trading remains available while verification/MFA setup is incomplete.
- Activation summarizes exchange environment, exact algorithm version, instrument, limits, stop/target, leverage and account. Explicit user confirmation is required for each live activation. No bot is started during installation, migration, login or page load.
- Activity and P&L come from reconciled exchange fills, fees, funding and positions. Unknown and stale values are visibly labeled; never show mock bots or optimistic success.

## Deployment and operations

- Add a separate production Compose configuration with no source bind mounts, non-root containers, private DB/Redis networks, explicit secrets, TLS reverse proxy, restricted trusted hosts/origins, request limits and immutable builds. Keep local development working.
- Run migrations as a one-shot deployment operation, not independently on every worker start. Back up and restore-test PostgreSQL before release. Do not launch the user's existing workers during isolated testing.
- Provide readiness checks for migration version, database/Redis, worker heartbeat, clock drift, account reconciliation and alert delivery. Entry eligibility becomes false when required evidence is stale. Financial recovery does not depend on the UI being open or on Redis being the sole source of truth.
- Emit durable audit events and structured metrics without credentials. Alert on unprotected/unknown exposure, reconciliation lag, worker death, key rejection, risk breaches and DB failures. Record operator acknowledgement. Alert channel configuration and delivery are acceptance requirements.
- Rollback disables entries first, reconciles/neutralizes managed exposure, then changes application versions only when schema-compatible. Never blindly roll back order ledgers or delete unresolved records.

## Implementation order and acceptance evidence

1. Add isolated PostgreSQL/Redis CI integration infrastructure and concurrency/restart tests for existing accounting, password reset and intent ownership. No user's database or exchange account is a test fixture.
2. Implement production configuration validation, session/MFA security and verified-user gating. Test CSRF, revocation, cross-user access, secret redaction and lockout recovery.
3. Add live schema, environment separation, account identity, read-only verification and readiness API/UI. Feature flag remains off.
4. Implement production transport and orchestration with replayable fault tests: lost submission response, crash before/after commit, partial fill, expired protection, user-stream disconnect, stale data, duplicate workers, rate limits and emergency close. No real order is submitted by automated tests.
5. Add actual exchange fill/P&L reporting, persistent risk policy and alerts. Test losses/fees/funding across UTC midnight and restart, and deposit/withdrawal adjustments.
6. Run genuine Binance demo acceptance on a dedicated demo account: authenticated verification, entry, fill reconciliation, exchange stop/target confirmation, strategy exit, stop-and-close, worker restart and unresolved-order recovery. Record redacted evidence tied to code revision, configuration and graph hash. This is an exchange-mutating test and is separately initiated for the designated demo account.
7. Deploy with production entries disabled; verify TLS, backups, alert delivery, heartbeat and production read-only account checks. Review all evidence. Enabling real orders and selecting funded limits require explicit user action after the result is reviewable.

Each step must pass focused tests and the existing suite without weakening assertions. A failed or unavailable acceptance test remains a blocker, not a checked box. Completion means passing release evidence and functioning controls, not merely implementing an adapter or setting an environment variable.

## Choices left to implementation

Module/file names, cookie/session storage details, vetted MFA package, metrics exporter, test fixtures and frontend component composition may be selected by the implementer within these constraints. Keep migrations additive and the existing demo API compatible. Do not create or commit secrets; do not commit unrelated existing work.

## Primary reference

[Binance USDⓈ-M futures trade API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade), consulted 2026-10-21: regular and conditional/algo orders have distinct endpoints; execution must reconcile both. Verify endpoint-specific request and response contracts again during implementation. All other requirements above are engineering design decisions, not claims of exchange guarantees.
