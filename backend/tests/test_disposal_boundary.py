"""Structural proof of "the LLM proposes, the server disposes" — not a narrated claim.

Two independent checks:
1. Import-graph check: no module under app/agent/ imports app.checkout or
   app.razorpay_client, even transitively. The LLM's code path physically cannot reach
   Razorpay.
2. Tool-schema check: none of the Gemini function declarations exposed to the model are
   named (or contain a name fragment implying) order creation, payment capture, or refunds.
"""
import ast
import os

import pytest

from app.agent.tools import FORBIDDEN_TOOL_NAME_FRAGMENTS, TOOL_SCHEMAS

AGENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "agent")
FORBIDDEN_MODULES = {"app.checkout", "app.razorpay_client"}


def _imported_module_names(filepath: str) -> set[str]:
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=filepath)

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


@pytest.mark.parametrize(
    "filename",
    [f for f in os.listdir(AGENT_DIR) if f.endswith(".py")],
)
def test_no_agent_module_imports_the_disposal_layer(filename):
    filepath = os.path.join(AGENT_DIR, filename)
    imported = _imported_module_names(filepath)
    violations = imported & FORBIDDEN_MODULES
    assert not violations, f"{filename} imports disposal-layer module(s): {violations}"


def test_tool_schema_exposes_no_money_moving_function():
    for tool in TOOL_SCHEMAS:
        name = tool["name"].lower()
        for fragment in FORBIDDEN_TOOL_NAME_FRAGMENTS:
            assert fragment not in name, f"tool '{tool['name']}' name implies money movement"


def test_tool_schema_only_contains_the_three_advisory_tools():
    names = {tool["name"] for tool in TOOL_SCHEMAS}
    assert names == {"search_catalog", "propose_cart", "check_mandate"}


def test_propose_cart_description_disclaims_pricing_authority():
    propose_cart = next(t for t in TOOL_SCHEMAS if t["name"] == "propose_cart")
    description = propose_cart["description"].lower()
    assert "does not" in description or "ignored" in description
