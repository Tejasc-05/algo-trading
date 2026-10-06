# Four-person development workflow

Keep one modular monolith and small pull requests. All members use the same
graph and API contracts in INTEGRATION.md. Suggested ownership:

| Member | Primary modules |
|---|---|
| 1 | Strategy schema, registry, safe evaluation, validator |
| 2 | React API integration, auth screens, data mapping, WebSocket client |
| 3 | SQLAlchemy models/migrations, paper account settlement, portfolio |
| 4 | CCXT normalization/cache, quant adapters, sentiment providers |

Use `codex/strategy-engine`, `codex/frontend-integration`,
`codex/paper-trading`, and `codex/market-sentiment` or your team's chosen branch
names. PRs should describe the user-facing behavior and validation results.
Assign one member to resolve schema changes and order Alembic revisions. Never
rewrite an applied migration; add a new revision. Keep account settlement inside
one transaction, and publish disposable events only after commit. API routes
coordinate services; strategy math has no database/exchange dependencies.

CI checks the backend tests with real quant packages and builds the existing
frontend. Market API tests inject deterministic data, avoiding network-driven
test failures. Add PostgreSQL concurrency tests before changing execution locks.
Use protected main/develop branches and review migrations, money accounting,
ownership and credential handling before merging. `.env`, local databases and
virtual environments are ignored and excluded from Docker build contexts.

The supplied stack image supports CCXT, Pandas/NumPy and VectorBT/Backtrader.
The final project report was not available in this handoff and has not been
used to infer extra requirements.
