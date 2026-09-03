"""_to_plain must recursively strip protobuf composite types so json.dumps in app/audit.py
never chokes on a real Gemini tool call's nested args (e.g. propose_cart's `items` list).
"""
from app.agent.gemini_client import _to_plain


class FakeMapComposite:
    """Mimics google.ai.generativelanguage's MapComposite: dict-like, not a real dict."""

    def __init__(self, data: dict):
        self._data = data

    def items(self):
        return self._data.items()


class FakeRepeatedComposite:
    """Mimics RepeatedComposite: iterable, not a real list."""

    def __init__(self, data: list):
        self._data = data

    def __iter__(self):
        return iter(self._data)


def test_plain_scalar_passthrough():
    assert _to_plain(5) == 5
    assert _to_plain("hello") == "hello"


def test_flat_map_composite_converted_to_dict():
    fake = FakeMapComposite({"product_id": 1, "qty": 2})
    result = _to_plain(fake)
    assert result == {"product_id": 1, "qty": 2}
    assert isinstance(result, dict)


def test_nested_repeated_composite_of_map_composites_converted_to_list_of_dicts():
    # This is the actual shape of propose_cart's args: {"items": [{"product_id":1,"qty":2}, ...]}
    fake = FakeMapComposite(
        {
            "items": FakeRepeatedComposite(
                [
                    FakeMapComposite({"product_id": 1, "qty": 2}),
                    FakeMapComposite({"product_id": 3, "qty": 1}),
                ]
            )
        }
    )
    result = _to_plain(fake)
    assert result == {"items": [{"product_id": 1, "qty": 2}, {"product_id": 3, "qty": 1}]}

    import json

    json.dumps(result)  # must not raise


def test_string_values_not_treated_as_iterables_of_characters():
    fake = FakeMapComposite({"query": "wireless mouse"})
    assert _to_plain(fake) == {"query": "wireless mouse"}
