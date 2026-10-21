# Multi-user Binance release preparation

The target audience is mainly India, with users connecting their own Binance accounts. The owner does not yet have a deployment server. **The application is not ready to trade real money.** This document records implemented foundations and explicit remaining work; it is not release approval.

## Implemented foundations

- Browser login uses a random opaque HttpOnly session cookie. Only its SHA-256 digest, owner, expiry and authentication version are stored. Production cookies use the `__Host-` prefix, Secure, SameSite=Strict and Path=/.
- Browser JavaScript no longer persists bearer tokens. Reload checks the server session; cookie-authenticated writes require a session-bound CSRF proof and an allowed Origin. Legacy bearer endpoints are development/test-only and unavailable in production.
- Logout revokes the session. Password reset invalidates earlier sessions and retains MFA. WebSockets revalidate their original session; the browser checks its current cookie before reconnecting after MFA rotates that session.
- Settings supports emailed verification links and authenticator enrollment. Verification links are hashed, expire after one hour, are single-use and owner-bound. TOTP secrets are encrypted; confirmation requires proof of possession, and consumed counters cannot be reused across login/step-up. Enrollment expires after ten minutes. Per-user/email and IP limits use Redis.
- Production credentials require verified email, MFA and a browser session with MFA confirmation in the last five minutes. Saving keys does not enable orders.
- Signed Binance verification uses GET requests to fixed Binance hosts only. It checks futures/read permissions, disabled withdrawals/transfers/spot trading, IP restriction, trading-enabled one-way/single-asset mode and a unique exchange-reported futures account alias. Missing permission fields fail verification. The alias is hashed before persistence; a unique constraint prevents two AlgoFlow users registering the same exchange account.
- `/api/live/readiness` reports account and release blockers. Setting `ENABLE_LIVE_TRADING=true` cannot bypass the missing execution service. Generic CCXT order placement remains disabled.
- Additive migrations `0010`–`0013` add sessions, verification/MFA state, verified live account identities and the execution-ledger foundation. Existing users start unverified with MFA disabled; no existing user has been automatically approved for live access.
- The internal order ledger persists intent and sending state before an injected transport call. It binds protection/close intents to an entry cycle, never resubmits ambiguous writes, retains exchange identity through malformed observations and prevents triggered protection from becoming open after delayed responses. Account fencing and PostgreSQL advisory locks serialize workers. No endpoint activates this component, and no production writer is connected. Unfinished runs prevent credential removal; pinned algorithm versions remain retained.
- A separate production deployment definition provides a non-root API/web build, TLS proxy, private database/Redis network, read-only application filesystems and explicit configuration validation. The API trusts forwarded client addresses only from the designated proxy IP. Migration-aware `/health/ready` returns 503 on a schema mismatch; `/health/live` is process liveness. These checks do not authorize trading.

## Current blockers

1. **Production execution remains unimplemented.** The ledger foundation is implemented, but its production orchestration, full fill/fee accounting, independent risk/recovery monitor, authenticated exchange stream, transfer-adjusted persistent daily loss policy, emergency close workflow, live fills/P&L UI and execution fault matrix must be implemented and reviewed. Do not repoint the demo transport at production.
2. **MFA recovery is incomplete.** Self-service factor replacement and recovery are intentionally unavailable. A password reset cannot remove an authenticator. Secure recovery and its notifications/revocation tests are required before a public release.
3. **No genuine demo acceptance has been performed for this release.** Verify actual entry, partial/complete fills, exchange stop/target orders, strategy exit, stop-and-close, restart and unknown-submission recovery on a dedicated demo account. Persist redacted evidence tied to a code revision and graph hash.
4. **Hosting is not provisioned.** An always-on deployment with a stable outbound IP, domain, HTTPS, monitoring, backups and a tested restore is still needed. A local browser test does not validate DNS/certificates, server failure or public attack exposure. Do not buy or deploy infrastructure just to bypass remaining engineering checks.
5. **SMTP needs actual delivery acceptance.** Browser QA uses a fixture mailer; tests do not demonstrate delivery to a real inbox. The current background-task mailer is not a durable delivery queue.
6. **India eligibility remains unverified.** Binance's reporting registration is not proof that AlgoFlow may offer automated futures services to Indian users. Establish product/account eligibility with Binance and review the platform's obligations before enabling the country. No residency, product entitlement or public-service approval is inferred from a successful account API request.
7. **Deployment acceptance is incomplete.** Verify exact image digests, dependency/image scans, proxy client-IP behavior, HTTPS cookies/CSRF, real alerts, worker/recovery liveness, resource limits and operational rollback on the selected host. The production configuration is preparation, not an instruction to launch a real-money service now.

## Local verification and evidence

The security flows were checked through a real browser against an isolated PostgreSQL/Redis backend: signup, session reload, email-verification completion, MFA setup, rejection of login without MFA, MFA login, reconnect after session rotation, mobile logout and protected-route redirects. This used fixture account data, a fixture authenticator and a fixture mailer; no exchange credentials or orders were used.

PostgreSQL integration checks apply the actual Alembic migrations and prove concurrent single consumption of a TOTP counter, a password-reset token and an email-verification token; they also prove concurrent ownership registration of one exchange account yields one success and one conflict, check the migration-aware health endpoint and prove password revocation wins before a sensitive live action. Ledger integration tests prove account-lock contention, restart fencing, committed-before-write state, idempotent replay without row-lock leakage and canceled-worker cleanup. SQLite remains the fast default suite.

Browser artifacts and local logs are under ignored `work/`. The production web image builds and the non-root, read-only web process was tested serving on a loopback port with capabilities dropped. A separate browser pass against the non-root API/web containers over local HTTPS verified production-cookie signup/reload/login/logout and the production-credential security gate. Its internal test CA is not public certificate acceptance. Public TLS and a complete deployed stack remain unverified. See the dated audit for coverage limitations; its localStorage finding is superseded by this follow-up.

### Verification snapshot — 2026-10-22

- 295 backend tests passed, including the new ledger regression suite.
- 11 PostgreSQL/Redis integration tests passed against migrations through `0013_live_order_ledger`; paused runs remain exclusive and an unresolved cycle cannot be marked stopped.
- Both API and web images built. Frontend build and lint passed with existing warnings. Earlier dependency audits found no known vulnerabilities in the tested resolved environments; these are not continuous production scans.
- Fixture browser checks passed, including the local HTTPS production-cookie flow. A forged `X-Forwarded-For` header did not become the login-rate-limit address, and the API used the forwarded Docker gateway address rather than the trusted proxy's own address. Public-host client-IP behavior still requires acceptance on the selected server.
- Temporary services created for these checks were stopped. The user's workers and database were not migrated or started by these tests.

## Reproduce isolated tests

From the repository root, with a Python 3.12 environment containing the backend requirements:

```sh
docker compose -p algoflow-readiness-tests -f backend/docker-compose.test.yml up -d --wait
python -m pytest -q backend/tests
python -m pytest -c backend/integration/pytest.ini -q backend/integration
npm run build
npm run lint
docker compose -p algoflow-readiness-tests -f backend/docker-compose.test.yml down
```

Integration tests deliberately delete test rows and flush test rate-limit buckets. They refuse any database name other than `algoflow_readiness_test` and any Redis endpoint outside loopback port 16389 DB 0. Never point them at a shared or user database. Do not run a browser QA process against the same disposable database while these tests clean it.

## Future deployment procedure

After implementation, legal/product checks and acceptance have passed:

1. Provision the selected server, stable outbound address and domain. Use the same public HTTPS origin for the frontend and API. Point DNS at the host and allow only required public ports; keep PostgreSQL/Redis private. If a CDN/load balancer is added, explicitly review its proxy trust chain.
2. Build and scan API/web images and record immutable digests. Fill `backend/.env.production` from `.env.production.example` on the host. Generate new signing/encryption/database secrets; do not copy test credentials or publish the file. Preserve the encryption key securely for restored credentials.
3. Back up the previous database and verify restore on a disposable database. Review migrations, then run the one-shot migration job separately from workers. Do not run migrations concurrently from worker startup.
4. Start services with real execution disabled and verify schema readiness, TLS/session behavior, SMTP, rate limits, monitoring and recovery alerts. No exchange worker is included in the preparation Compose file.
5. Enable a narrowly limited real-money release only after the execution implementation, genuine demo acceptance and operational evidence have been reviewed. Each user must explicitly review and confirm their pinned strategy and monetary limits. An installation or successful login must never activate a bot.

Example commands for the selected, reviewed deployment (not run against the current user's data):

```sh
docker build -f backend/Dockerfile.production -t your-api-reviewed-tag backend
docker build -f Dockerfile.web -t your-web-reviewed-tag .
docker compose --env-file backend/.env.production -f backend/docker-compose.production.yml run --rm migrate
docker compose --env-file backend/.env.production -f backend/docker-compose.production.yml up -d api web
```

The sample Compose file keeps execution disabled. Turning a flag on is not an acceptance test. Rollback must preserve financial ledgers and reconcile any managed exposure before changing worker versions.

## Primary sources checked

- [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) and [CSRF protection](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
- [PyOTP implementation and replay guidance](https://pyauth.github.io/pyotp/).
- [Binance futures account API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account) and [API permission endpoint](https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/account).
- [Binance licences/registrations](https://www.binance.com/en-GB/legal/licenses%20), [Binance futures agreement access](https://www.binance.com/en-IN/support/faq/detail/360033180732) and [Indian government description of VDA reporting obligations](https://pib.gov.in/Pressreleaseshare.aspx?PRID=1991372&lang=2&reg=48). These sources do not establish AlgoFlow's derivatives-service eligibility.
