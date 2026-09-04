import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.db import Base, SessionLocal, engine
from app.routes import audit, autopay, chat, mcp, stats, ucp, webhooks
from app.seed import seed_if_empty

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("trustrail")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    yield


def create_app(*, enable_demo_routes: bool | None = None) -> FastAPI:
    """Factory rather than a module-level singleton, so tests can build an app with a
    different ENABLE_DEMO_ROUTES (see tests/test_demo_routes_gating.py)."""
    if enable_demo_routes is None:
        enable_demo_routes = config.ENABLE_DEMO_ROUTES

    app = FastAPI(
        title="TrustRail",
        description="Deterministic checkout gateway for AI shopping agents",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat.router)
    app.include_router(webhooks.router)
    app.include_router(ucp.router)
    app.include_router(audit.router)
    app.include_router(mcp.router)
    app.include_router(autopay.router)
    app.include_router(stats.router)

    if enable_demo_routes:
        from app.routes import demo

        app.include_router(demo.router)
    else:
        logger.info("ENABLE_DEMO_ROUTES is false — /demo/* endpoints are not mounted")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
