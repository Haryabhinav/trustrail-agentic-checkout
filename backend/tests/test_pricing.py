import pytest

from app.pricing import InsufficientStockError, UnknownProductError, price_cart


def test_computes_canonical_total_from_db_not_from_input(db_session):
    # attacker/hallucinated price field is not even part of the accepted input shape —
    # price_cart's items only ever carry product_id/qty (see checkout.py's clean_items)
    priced = price_cart(db_session, [{"product_id": 1, "qty": 2}])
    assert priced.total_inr == 799 * 2
    assert priced.items[0]["unit_price_inr"] == 799


def test_unknown_product_id_raises(db_session):
    with pytest.raises(UnknownProductError):
        price_cart(db_session, [{"product_id": 99999, "qty": 1}])


def test_insufficient_stock_raises(db_session):
    with pytest.raises(InsufficientStockError):
        price_cart(db_session, [{"product_id": 4, "qty": 999}])  # earbuds, stock 8


def test_empty_cart_rejected(db_session):
    with pytest.raises(ValueError):
        price_cart(db_session, [])


def test_invalid_quantity_rejected(db_session):
    with pytest.raises(ValueError):
        price_cart(db_session, [{"product_id": 1, "qty": 0}])


def test_single_category_reported(db_session):
    priced = price_cart(db_session, [{"product_id": 1, "qty": 1}, {"product_id": 2, "qty": 1}])
    assert priced.category == "electronics"


def test_mixed_category_reported_as_mixed(db_session):
    priced = price_cart(db_session, [{"product_id": 1, "qty": 1}, {"product_id": 5, "qty": 1}])
    assert priced.category == "mixed"


def test_multi_line_total_is_sum_of_line_totals(db_session):
    priced = price_cart(db_session, [{"product_id": 1, "qty": 3}, {"product_id": 5, "qty": 2}])
    expected = 799 * 3 + 649 * 2
    assert priced.total_inr == expected


def test_duplicate_product_id_lines_are_each_priced_independently(db_session):
    # Two separate lines for the same product must not collapse into one — this exercises the
    # batched-fetch path's dict lookup being reused correctly across repeated line items.
    priced = price_cart(db_session, [{"product_id": 1, "qty": 1}, {"product_id": 1, "qty": 2}])
    assert len(priced.items) == 2
    assert priced.total_inr == 799 * 3


def test_pricing_an_n_item_cart_issues_exactly_one_product_query(db_session):
    # Regression test for the N+1 fix: price_cart used to issue one SELECT per line item.
    # It must now issue exactly one SELECT ... WHERE id IN (...) regardless of cart size.
    from sqlalchemy import event

    engine = db_session.get_bind()
    queries = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        if "products" in statement.lower():
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        price_cart(
            db_session,
            [{"product_id": 1, "qty": 1}, {"product_id": 2, "qty": 1}, {"product_id": 3, "qty": 1}],
        )
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert len(queries) == 1, f"expected exactly 1 product query for a 3-item cart, got {len(queries)}"
    assert " in " in queries[0].lower() or " IN " in queries[0]
