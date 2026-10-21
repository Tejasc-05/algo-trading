"""Dedicated PostgreSQL tests; refuse to touch any other database name."""
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

test_url = os.environ.get('ALGOFLOW_TEST_DATABASE_URL',
    'postgresql+asyncpg://algoflow_test:disposable-test-only@127.0.0.1:15439/algoflow_readiness_test')
parsed = urlparse(test_url)
if parsed.path != '/algoflow_readiness_test' or not test_url.startswith('postgresql+asyncpg://'):
    raise RuntimeError('Integration tests require the dedicated algoflow_readiness_test database.')
os.environ['DATABASE_URL'] = test_url
os.environ['REDIS_URL'] = os.environ.get('ALGOFLOW_TEST_REDIS_URL', 'redis://127.0.0.1:16389/0')
test_redis = urlparse(os.environ['REDIS_URL'])
if test_redis.hostname not in {'127.0.0.1', 'localhost'} or test_redis.port != 16389 or test_redis.path != '/0':
    raise RuntimeError('Integration tests require the dedicated loopback Redis on port 16389, DB 0.')
os.environ['ENVIRONMENT'] = 'development'
os.environ['DEBUG'] = 'false'
os.environ['JWT_SECRET'] = 'integration-test-only-secret-at-least-32-bytes'
os.environ['ENCRYPTION_KEY'] = Fernet.generate_key().decode()
os.environ['CORS_ORIGINS'] = 'http://localhost:5173'
os.environ['ENABLE_LIVE_TRADING'] = 'false'

from app.database.database import engine, AsyncSessionLocal
from app.database.models import Base
from app.main import app
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text


@pytest.fixture(scope='session', autouse=True)
def migrations():
    import sys
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True)


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    # Explicit, fixed allowlisted database above; never load the user's .env URL.
    async with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            await connection.execute(table.delete())
    # This endpoint is explicitly reserved for the disposable Compose project.
    # Persistent rate buckets otherwise make repeated race tests order-dependent.
    import redis.asyncio as redis
    async with redis.Redis.from_url(os.environ['REDIS_URL']) as client:
        await client.flushdb()
    yield
    # Dispose per loop: asyncpg connections cannot be reused across pytest loops.
    await engine.dispose()
    from app.redis.client import redis_pool
    await redis_pool.disconnect()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as value:
        yield value
