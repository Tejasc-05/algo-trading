# Multi-user Binance Live Readiness Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task in the current session. Preserve existing uncommitted changes; do not commit unrelated work or submit real orders.

**Goal:** Prepare AlgoFlow's multi-user security and execution boundaries for a separately accepted Binance futures release.

**Architecture:** Keep the modular monolith, existing React UI and demo runner. Add database-backed browser sessions, verified-email/MFA security and a separate fail-closed live readiness boundary. Exchange writes remain unavailable until every release acceptance requirement is implemented and verified.

**Tech Stack:** React/TypeScript, FastAPI, SQLAlchemy/Alembic, PostgreSQL, Redis, Pytest and Docker.

**Spec:** `docs/superpowers/specs/2026-10-21-binance-live-readiness-design.md`

## Global constraints

- Multi-user signup; ownership checked server-side on every resource.
- Binance USDⓈ-M futures first, Delta later; isolated margin and 1x initial scope.
- No production orders during tests, installation, migrations or login.
- No secrets committed or printed; no modification of existing user data during isolated tests.
- Retain all prior regression assertions and explicit disabled-execution behavior until acceptance is complete.

## Review focus

- A stolen or reset session cannot use old security credentials or complete another user's verification.
- A cross-site request cannot mutate cookie-authenticated account state.
- A reused TOTP or verification token cannot repeat a sensitive action, including concurrent requests.
- A worker restart or paused entry state cannot silently abandon managed exposure.
- SQLite passing cannot substitute for PostgreSQL row-lock and migration evidence.

### Task 1: Browser session boundary

Files: `backend/app/auth/sessions.py`, security database models and additive migration, auth/dependencies/WebSocket middleware, `src/lib/api.ts`, protected layout and auth pages.

Interfaces: issue opaque session/CSRF tokens; store only token hashes and auth version. Resolve active sessions via database; rotate on login; revoke on logout, expiry and password reset. Same-origin CSRF headers protect cookie writes. Browser never persists bearer tokens.

- [x] Add failing API tests for HttpOnly cookies, CSRF, origin mismatch, logout/revocation and expiry.
- [x] Implement `/auth/browser/{login,register,session,logout}` without breaking explicit bearer API clients in development. Disable bearer access in production.
- [x] Migrate browser authentication and WebSockets to cookies; check session on initial page load.
- [x] Run focused tests, frontend build and browser login/logout/reload checks.

### Task 2: Email verification and MFA

Files: `backend/app/auth/account_security.py`, API security routes, schema/model migration, account security React panel.

Interfaces: request/complete hashed single-use verification links; TOTP enrollment with password proof, encrypted pending secret, proof of possession and replay prevention; MFA login and five-minute step-up. Password reset revokes sessions while retaining MFA. Do not implement insecure MFA bypass/recovery.

- [x] Add failing tests for wrong user, expired/reused link, failed/replayed MFA, enrollment replacement and reset retaining MFA.
- [x] Implement security status, email verification, MFA enrollment/confirmation and step-up routes with shared rate limits.
- [x] Add functional settings controls and login MFA input using existing UI components.
- [x] Verify API and browser flows; document administrator-assisted MFA recovery as unavailable until secure recovery is implemented.

### Task 3: Release readiness and production boundary

Files: live readiness service/routes, config validation, live trading status panel, production deployment config and release runbook.

Interfaces: authenticated `/live/readiness` returns evidence-based blockers; no invented success values. User requirements include verified email, MFA and recent step-up. Operator requirements include PostgreSQL/TLS/production secrets, explicit jurisdiction/policy, tested alerts/backups, and genuine demo lifecycle evidence tied to revision. Missing implementation remains a hard blocker even if the flag is true.

- [x] Test cross-user isolation, missing security requirements and flag-bypass rejection. Execution acceptance evidence is not implemented; its readiness check remains false.
- [x] Implement readable blockers, reject credential saving without account security in production and keep generic CCXT order execution disabled.
- [x] Add a production build configuration with TLS proxy, private infrastructure, no bind-mounted source and a separate migration job.
- [x] Document exact external inputs and outstanding execution acceptance. Never label this task itself a completed live adapter.

### Task 4: PostgreSQL integration and recovery evidence

Files: isolated Docker test services, PostgreSQL integration tests, CI service job.

Interfaces: tests use a disposable database with explicit test-only URL; run additive Alembic migrations and concurrent password-reset/session/MFA tests against real locks.

- [x] Add concurrency tests that prove only one consumer succeeds and reset invalidates sessions.
- [x] Run on isolated PostgreSQL/Redis without existing workers; record results.
- [x] Add CI gates and clear commands. Stop only test infrastructure created for this task.

### Task 5: Production execution and release acceptance (dependent work)

The dedicated live transport, account-identity registration, account-scoped execution ledger/coordination, persistent UTC daily risk policy, independent monitoring/recovery worker, authenticated user stream, durable alerts, actual fill/P&L UI and exchange fault matrix are required by the spec. Implement these only after the preceding security/integration boundary is verified; do not repoint the demo transport or bypass tests. Genuine demo exchange writes, public deployment, jurisdiction eligibility, alert delivery, backup restore and enabling funded limits require designated external accounts/infrastructure and recorded acceptance evidence. Any missing item remains an explicit blocker in Task 3.

Progress is tracked honestly per task; code readiness and operational acceptance are separate outcomes.


## Execution foundation progress (2026-10-22)

- [x] Fixed-host, signed read-only Binance permissions/account verification, owner filtering and unique exchange-account registration.
- [x] Additive `0013` migration: account fencing, pinned runs, durable order intents, cycle identity and audit events.
- [x] Persist intent and SENDING state before injected transport; never resend SENDING/UNKNOWN orders.
- [x] Keep known order identity/fills through malformed responses; prevent triggered-stop regression and cross-cycle order replay.
- [x] PostgreSQL advisory contention, replacement fencing, cancellation cleanup and replay lock-release tests.
- [x] Retain pinned algorithms and prevent credential removal for unfinished runs.
- [ ] Dedicated production transport and orchestration, authenticated stream, reconciliation/recovery worker and confirmed protection/close lifecycle.
- [ ] Persistent account/day/session risk accounting with transfers, fees and funding; operator caps and explicit user limits.
- [ ] Durable alerts, actual exchange fill/P&L UI and full fault acceptance matrix.
- [ ] Secure MFA recovery, durable verification-mail delivery and operational/exchange acceptance.

The ledger is an internal component with a test transport. No API starts a live run, and no production exchange write path is enabled. Completing the security tasks does not complete Task 5 or approve a public launch.
