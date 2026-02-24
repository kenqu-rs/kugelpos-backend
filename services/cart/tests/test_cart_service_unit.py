# Copyright 2025 masa@kugel  # # Licensed under the Apache License, Version 2.0 (the "License");  # you may not use this file except in compliance with the License.  # You may obtain a copy of the License at  # #     http://www.apache.org/licenses/LICENSE-2.0  # # Unless required by applicable law or agreed to in writing, software  # distributed under the License is distributed on an "AS IS" BASIS,  # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  # See the License for the specific language governing permissions and  # limitations under the License.
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.cart_service import CartService
from app.models.documents.cart_document import CartDocument
from app.exceptions import LineItemNotFoundException
from app.exceptions.cart_error_codes import CartErrorCode


# --- Helpers ---


def make_cart_doc(line_items_config: list[dict]) -> CartDocument:
    """
    Create a CartDocument with the given line item configurations.

    Args:
        line_items_config: List of dicts with keys: quantity, unit_price, is_cancelled
    """
    items = []
    for i, cfg in enumerate(line_items_config):
        item = CartDocument.CartLineItem(
            line_no=i + 1,
            item_code=f"ITEM-{i + 1:02d}",
            quantity=cfg.get("quantity", 1),
            unit_price=cfg.get("unit_price", 100.0),
            amount=cfg.get("quantity", 1) * cfg.get("unit_price", 100.0),
            is_cancelled=cfg.get("is_cancelled", False),
        )
        items.append(item)
    return CartDocument(cart_id="test-cart-001", line_items=items)


# --- Fixtures ---


@pytest_asyncio.fixture
async def cart_service():
    """
    CartService instance with all external dependencies mocked.

    CartStrategyManager is patched during __init__ to suppress plugin file loading.
    Private async methods (__get_cached_cart_async, __subtotal_async, __cache_cart_async)
    are overridden per-test via AsyncMock.
    """
    patcher = patch("app.services.cart_service.CartStrategyManager")
    mock_strategy_cls = patcher.start()
    mock_strategy_cls.return_value.load_strategies.return_value = []

    service = CartService(
        terminal_info=MagicMock(),
        cart_repo=MagicMock(),
        terminal_counter_repo=MagicMock(),
        settings_master_repo=MagicMock(),
        tax_master_repo=MagicMock(),
        item_master_repo=MagicMock(),
        payment_master_repo=MagicMock(),
        store_info_repo=MagicMock(),
        tran_service=MagicMock(),
        cart_id="test-cart-001",
    )

    patcher.stop()

    yield service


# --- Tests: update_line_item_quantity_in_cart_async ---


class TestUpdateLineItemQuantityValidation:
    """
    Unit tests for the validation logic added to
    CartService.update_line_item_quantity_in_cart_async.

    All external I/O (Dapr state store, subtotal calculation) is mocked so
    tests run without any running services.
    """

    @pytest.mark.asyncio
    async def test_line_no_exceeds_item_count_raises_exception(self, cart_service):
        """line_no larger than number of items raises LineItemNotFoundException (402006)"""
        cart_doc = make_cart_doc([{"quantity": 2}])  # only line_no=1 exists
        cart_service._CartService__get_cached_cart_async = AsyncMock(return_value=cart_doc)
        cart_service.state_manager.check_event_sequence = MagicMock()

        with pytest.raises(LineItemNotFoundException) as exc_info:
            await cart_service.update_line_item_quantity_in_cart_async(line_no=99, quantity=3)

        assert exc_info.value.error_code == CartErrorCode.LINE_ITEM_NOT_FOUND

    @pytest.mark.asyncio
    async def test_line_no_zero_raises_exception(self, cart_service):
        """line_no=0 (below minimum) raises LineItemNotFoundException (402006)"""
        cart_doc = make_cart_doc([{"quantity": 1}])
        cart_service._CartService__get_cached_cart_async = AsyncMock(return_value=cart_doc)
        cart_service.state_manager.check_event_sequence = MagicMock()

        with pytest.raises(LineItemNotFoundException) as exc_info:
            await cart_service.update_line_item_quantity_in_cart_async(line_no=0, quantity=3)

        assert exc_info.value.error_code == CartErrorCode.LINE_ITEM_NOT_FOUND

    @pytest.mark.asyncio
    async def test_cancelled_line_raises_exception(self, cart_service):
        """line_no pointing to a cancelled item raises LineItemNotFoundException (402006)"""
        cart_doc = make_cart_doc([
            {"quantity": 1, "is_cancelled": True},   # line_no=1 (cancelled)
            {"quantity": 2, "is_cancelled": False},  # line_no=2 (active)
        ])
        cart_service._CartService__get_cached_cart_async = AsyncMock(return_value=cart_doc)
        cart_service.state_manager.check_event_sequence = MagicMock()

        with pytest.raises(LineItemNotFoundException) as exc_info:
            await cart_service.update_line_item_quantity_in_cart_async(line_no=1, quantity=5)

        assert exc_info.value.error_code == CartErrorCode.LINE_ITEM_NOT_FOUND

    @pytest.mark.asyncio
    async def test_valid_input_updates_quantity(self, cart_service):
        """Valid line_no with active item → quantity is updated and cart is returned"""
        cart_doc = make_cart_doc([{"quantity": 2}])
        cart_service._CartService__get_cached_cart_async = AsyncMock(return_value=cart_doc)
        cart_service.state_manager.check_event_sequence = MagicMock()
        cart_service._CartService__subtotal_async = AsyncMock(return_value=cart_doc)
        cart_service._CartService__cache_cart_async = AsyncMock()

        result = await cart_service.update_line_item_quantity_in_cart_async(line_no=1, quantity=7)

        assert result.line_items[0].quantity == 7

    @pytest.mark.asyncio
    async def test_only_target_line_is_updated(self, cart_service):
        """Only the specified line_no is updated; other lines remain unchanged"""
        cart_doc = make_cart_doc([
            {"quantity": 1},  # line_no=1
            {"quantity": 3},  # line_no=2
        ])
        cart_service._CartService__get_cached_cart_async = AsyncMock(return_value=cart_doc)
        cart_service.state_manager.check_event_sequence = MagicMock()
        cart_service._CartService__subtotal_async = AsyncMock(return_value=cart_doc)
        cart_service._CartService__cache_cart_async = AsyncMock()

        await cart_service.update_line_item_quantity_in_cart_async(line_no=1, quantity=9)

        assert cart_doc.line_items[0].quantity == 9   # updated
        assert cart_doc.line_items[1].quantity == 3   # unchanged
