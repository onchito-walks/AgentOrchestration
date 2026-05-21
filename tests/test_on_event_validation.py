import pytest
from src.sdk.decorators import on_event


class TestOnEventValidation:
    """Tests for on_event() rejecting blank event handler names (bounty #1050)."""

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="non-blank"):
            on_event("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError, match="non-blank"):
            on_event("   ")

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="non-blank"):
            on_event(None)

    def test_valid_event_type_passes(self):
        """A non-blank event_type should work without error."""
        @on_event("user.created")
        async def handle_user_created(self):
            pass

        assert handle_user_created.__event_handler__ == "user.created"

    def test_valid_event_type_with_spaces_passes(self):
        """An event_type with surrounding whitespace but non-blank core should pass."""
        @on_event("  order.placed  ")
        async def handle_order_placed(self):
            pass

        assert handle_order_placed.__event_handler__ == "  order.placed  "
