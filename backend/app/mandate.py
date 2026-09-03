"""Deterministic spend/category gate. No LLM involved — pure function, fully unit-testable."""
from dataclasses import dataclass


@dataclass
class MandateState:
    max_spend_inr: int
    allowed_categories: list[str]
    spent_so_far_inr: int


def check_mandate(cart_total_inr: int, category: str, mandate: MandateState) -> tuple[bool, str]:
    """Returns (allowed, reason). Pure — same inputs always produce the same output."""
    if cart_total_inr <= 0:
        return False, "cart total must be positive"

    if category not in mandate.allowed_categories:
        return False, (
            f"category '{category}' is not in the allowed list "
            f"({', '.join(mandate.allowed_categories)})"
        )

    remaining = mandate.max_spend_inr - mandate.spent_so_far_inr
    if cart_total_inr > remaining:
        return False, (
            f"cart total INR {cart_total_inr} exceeds remaining mandate budget "
            f"INR {remaining} (max INR {mandate.max_spend_inr}, already spent INR {mandate.spent_so_far_inr})"
        )

    return True, "within mandate"
