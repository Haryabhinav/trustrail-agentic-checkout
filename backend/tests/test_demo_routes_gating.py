from fastapi.testclient import TestClient

from app.db import get_db
from app.main import create_app


def _client_with(*, enable_demo_routes: bool, db_session) -> TestClient:
    app = create_app(enable_demo_routes=enable_demo_routes)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_demo_routes_mounted_by_default(db_session):
    client = _client_with(enable_demo_routes=True, db_session=db_session)
    resp = client.post("/demo/simulate-gateway-failure", json={"attempts": 1})
    assert resp.status_code == 200


def test_demo_routes_not_mounted_when_disabled(db_session):
    # /demo/agent-autopay-purchase and /demo/simulate-injection can move real money with a
    # single unauthenticated request (see security review) — a deployment that sets
    # ENABLE_DEMO_ROUTES=false must not expose them at all, not just refuse to act on them.
    client = _client_with(enable_demo_routes=False, db_session=db_session)

    assert client.post("/demo/simulate-gateway-failure", json={"attempts": 1}).status_code == 404
    assert client.post("/demo/simulate-injection", json={}).status_code == 404
    assert client.post("/demo/agent-autopay-purchase", json={}).status_code == 404

    # every other router must still be mounted normally
    assert client.get("/health").status_code == 200
    assert client.get("/catalog").status_code == 200
    assert client.get("/autopay/status").status_code == 200
