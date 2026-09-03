from app.mandate import MandateState, check_mandate

BASE = MandateState(
    max_spend_inr=5000, allowed_categories=["electronics", "groceries"], spent_so_far_inr=0
)


def test_within_budget_and_allowed_category_passes():
    allowed, reason = check_mandate(2000, "electronics", BASE)
    assert allowed is True
    assert "within" in reason


def test_disallowed_category_blocked():
    allowed, reason = check_mandate(100, "office-supplies", BASE)
    assert allowed is False
    assert "not in the allowed list" in reason


def test_over_budget_blocked():
    allowed, reason = check_mandate(6000, "electronics", BASE)
    assert allowed is False
    assert "exceeds remaining mandate budget" in reason


def test_exact_remaining_budget_passes_boundary():
    allowed, _ = check_mandate(5000, "electronics", BASE)
    assert allowed is True


def test_one_rupee_over_remaining_budget_fails_boundary():
    allowed, _ = check_mandate(5001, "electronics", BASE)
    assert allowed is False


def test_respects_already_spent_amount():
    state = MandateState(max_spend_inr=5000, allowed_categories=["electronics"], spent_so_far_inr=4500)
    allowed, reason = check_mandate(600, "electronics", state)
    assert allowed is False
    assert "500" in reason  # remaining budget is 500


def test_zero_or_negative_total_rejected():
    allowed, reason = check_mandate(0, "electronics", BASE)
    assert allowed is False
    allowed, reason = check_mandate(-100, "electronics", BASE)
    assert allowed is False


def test_pure_function_same_input_same_output():
    r1 = check_mandate(1000, "electronics", BASE)
    r2 = check_mandate(1000, "electronics", BASE)
    assert r1 == r2
