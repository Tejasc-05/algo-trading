"""FastAPI application factory: assembles middleware, exception handlers, and
every route module behind one consistent app instance."""
from contextlib import asynccontextmanager
import hmac

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.database.database import engine

settings = get_settings()
configure_logging(debug=settings.debug)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AlgoFlow API starting", extra={"environment": settings.environment})
    yield
    await engine.dispose()
    from app.redis.client import redis_pool
    await redis_pool.disconnect()
    logger.info("AlgoFlow API shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AlgoFlow API",
        description="No-code AI-powered algorithmic trading platform — backend engine.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    if settings.environment == 'production':
        from urllib.parse import urlsplit
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(settings.cors_origins_list[0]).hostname])

    @app.middleware('http')
    async def private_api_responses(request, call_next):
        from app.auth.sessions import cookie_name, csrf_token
        from fastapi.responses import JSONResponse
        raw = request.cookies.get(cookie_name())
        if request.url.path.startswith('/api/') and request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            browser_entry = request.url.path in {'/api/auth/browser/login', '/api/auth/browser/register'}
            origin = request.headers.get('origin')
            bad_origin = (raw or browser_entry) and origin not in settings.cors_origins_list
            bad_token = raw and not browser_entry and not hmac.compare_digest(request.headers.get('x-csrf-token', '').encode(), csrf_token(raw).encode())
            if bad_origin or bad_token:
                return JSONResponse({'error': {'code': 'CSRF_REJECTED', 'message': 'Reload the page and try again.'}},
                    status_code=403, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            # Account data, credentials and recovery responses must not persist
            # in browser or shared-proxy HTTP caches.
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        if settings.environment == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    app.include_router(health_router)
    app.include_router(api_router)

    from app.websocket.manager import websocket_endpoint
    app.add_api_websocket_route("/ws", websocket_endpoint)

    return app


app = create_app()
