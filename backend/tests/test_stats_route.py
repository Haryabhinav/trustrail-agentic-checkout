from app.audit import log as audit_log


def test_stats_defaults(app_client):
    resp = app_client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["max_spend_inr"] == 5000
    assert body["spent_so_far_inr"] == 0
    assert body["orders_count"] == 0
    assert body["autopay_status"] == "none"
    assert set(body["allowed_categories"]) == {"electronics", "groceries", "office-supplies"}


def test_stats_counts_successful_orders_and_blocked_events(app_client, db_session):
    audit_log(db_session, session_id="a", event_type="order_created", status="ok")
    audit_log(db_session, session_id="a", event_type="autopay_charge", status="ok")
    audit_log(db_session, session_id="a", event_type="order_created", status="error")  # not counted
    audit_log(db_session, session_id="a", event_type="rejected_injection", status="blocked")

    resp = app_client.get("/stats")
    body = resp.json()
    assert body["orders_count"] == 2
    assert body["blocked_count"] == 1


def test_stats_audit_counts_use_a_single_query(app_client, db_session):
    # Regression test: orders_count and blocked_count used to be two separate COUNT(*)
    # queries against audit_log; they're now one query with conditional aggregation. This
    # endpoint is polled every 2s by the frontend, so the round-trip count matters.
    from sqlalchemy import event

    audit_log(db_session, session_id="a", event_type="order_created", status="ok")
    audit_log(db_session, session_id="a", event_type="rejected_injection", status="blocked")

    engine = db_session.get_bind()
    queries = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        if "audit_log" in statement.lower() and "select" in statement.lower():
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        app_client.get("/stats")
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert len(queries) == 1, f"expected exactly 1 audit_log query for stats, got {len(queries)}"
