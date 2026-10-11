# AlgoFlow backend

FastAPI modular monolith for the existing React/React Flow frontend. PostgreSQL is the source of truth; Redis supplies cache, rate limits and private WebSocket events.

## Start

Use Python 3.12. Copy `.env.example` to `.env` and set a random JWT secret and valid Fernet encryption key. For Docker, keep the provided postgres/redis hostnames. For local Python, use localhost and running PostgreSQL/Redis services.

```sh
cd backend
cp .env.example .env
# Set JWT_SECRET and ENCRYPTION_KEY before starting
docker compose up --build
```

Compose starts API, PostgreSQL, Redis, the paper worker and the Binance Futures demo worker. The API applies Alembic migrations before serving. Swagger is at http://localhost:8000/docs. Start the existing frontend from the repository root using npm run dev; Vite proxies /api and /ws.

For local development:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-quant.txt
alembic upgrade head
uvicorn app.main:app --reload
# Separate terminal, same environment:
python -m app.paper_trading.worker
```

## Verify

```sh
pytest -q
# Repository root:
npm ci
npm run build
```

Tests use SQLite, fake Redis and injected candles. Actual VectorBT and Backtrader packages are exercised. Docker/PostgreSQL migration checks are separate.

Auth, immutable strategy versions, graph validation/evaluation, CCXT reads, backtesting adapters, transactional spot/futures paper fills, isolated futures scenarios, account-scoped history and diagnostics, closed-candle worker processing and Redis/WebSocket infrastructure are implemented. Unsupported sentiment providers report unavailable. Real trading cannot execute, including when the configuration flag is enabled.

Read [INTEGRATION.md](docs/INTEGRATION.md) for the frontend graph, endpoints, simulation conventions, event envelopes and remaining limitations. Read [TEAM_WORKFLOW.md](docs/TEAM_WORKFLOW.md) for four-person development boundaries.

News sentiment defaults to key-free publisher RSS + local CPU FinBERT, with optional NewsAPI/hosted inference, with explicit feed delay, source evidence and Redis caching. Configure backend credentials using [SENTIMENT.md](docs/SENTIMENT.md). It does not feed trading orders; CryptoPanic/social integrations remain unavailable.

Binance Futures demo sessions support owned, pinned strategy versions, explicit long/short/close actions, isolated 1x positions, exposure and loss limits, durable order reconciliation and exchange-held stop loss/take profit. Read [BINANCE_FUTURES_DEMO.md](docs/BINANCE_FUTURES_DEMO.md) for setup and acceptance checks. Authenticated exchange fills still require genuine demo credentials and acceptance testing; production execution remains disabled.

Paper account controls, isolated futures simulation and known assumptions: [PAPER_TRADING.md](docs/PAPER_TRADING.md).
