import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret")
os.environ.setdefault("MANDATE_MAX_SPEND_INR", "5000")
os.environ.setdefault("MANDATE_ALLOWED_CATEGORIES", "electronics,groceries,office-supplies")
os.environ.setdefault("DATABASE_URL", "sqlite:///./.test_trustrail.db")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Mandate, Product
from app.seed import PRODUCTS


@pytest.fixture()
def db_session():
    # StaticPool is required for an in-memory sqlite db under TestClient: without it, each
    # new connection (e.g. from the anyio worker thread FastAPI's TestClient runs on) gets its
    # own private, empty :memory: database, silently orphaning the fixture's seeded data.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    for p in PRODUCTS:
        session.add(Product(**p))
    session.add(
        Mandate(id=1, max_spend_inr=5000, allowed_categories="electronics,groceries,office-supplies", spent_so_far_inr=0)
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def app_client(db_session):
    """FastAPI TestClient wired to the in-memory db_session fixture via dependency override."""
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    # Skip the real startup seeding/create_all against the default sqlite file — the
    # in-memory db_session fixture is already seeded.
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
