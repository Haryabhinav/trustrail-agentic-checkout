from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, SessionLocal, engine
from app.routes import audit, autopay, chat, demo, mcp, ucp, webhooks
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="TrustRail",
    description="Deterministic checkout gateway for AI shopping agents",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(webhooks.router)
app.include_router(ucp.router)
app.include_router(audit.router)
app.include_router(demo.router)
app.include_router(mcp.router)
app.include_router(autopay.router)


@app.get("/health")
def health():
    return {"status": "ok"}
