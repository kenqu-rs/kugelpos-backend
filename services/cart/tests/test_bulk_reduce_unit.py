# Copyright 2025 masa@kugel  # # Licensed under the Apache License, Version 2.0 (the "License");  # you may not use this file except in compliance with the License.  # You may obtain a copy of the License at  # #     http://www.apache.org/licenses/LICENSE-2.0  # # Unless required by applicable law or agreed to in writing, software  # distributed under the License is distributed on an "AS IS" BASIS,  # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  # See the License for the specific language governing permissions and  # limitations under the License.
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.cart_service import CartService
from app.models.documents.cart_document import CartDocument
from app.exceptions import ItemNotFoundException, ItemQuantityReductionExceedsException
from app.exceptions.cart_error_codes import CartErrorCode
from app.api.common.schemas import BaseBulkQuantityReductionItem, BaseBulkQuantityReductionRequest
from app.enums.cart_status import CartStatus


def make_line_item(item_code: str, quantity: int, is_cancelled: bool = False) -> CartDocument.CartLineItem:
    """Helper to build a CartLineItem for tests."""
    item = CartDocument.CartLineItem()
    item.item_code = item_code
    item.quantity = quantity
    item.is_cancelled = is_cancelled
    item.discounts = []
    item.discounts_allocated = []
    item.unit_price = 100.0
    item.amount = float(quantity * 100)
    item.line_no = 1
    return item


def make_cart_doc(*line_items: CartDocument.CartLineItem) -> CartDocument:
    """Helper to build a CartDocument with given line items."""
    cart = CartDocument()
    cart.cart_id = "test-cart-id"
    cart.status = CartStatus.EnteringItem.value
    cart.line_items = list(line_items)
    cart.masters = CartDocument.ReferenceMasters()
    return cart


class TestBulkReduceLineItemQuantityInCartAsync:
    """Unit tests for CartService.bulk_reduce_line_item_quantity_in_cart_async"""

    @pytest.fixture
    def service(self):
        """CartService with all external dependencies mocked."""
        with patch.object(CartService, "__init__", lambda self, **kwargs: None):
            svc = CartService.__new__(CartService)

        svc.cart_id = "test-cart-id"
        svc.terminal_info = MagicMock()
        svc.cart_repo = MagicMock()
        svc.item_master_repo = MagicMock()
        svc.item_master_repo.item_master_documents = []
        svc.tax_master_repo = MagicMock()
        svc.settings_master_repo = MagicMock()
        svc.payment_master_repo = MagicMock()
        svc.current_cart = None

        # State manager: allow all events by default
        svc.state_manager = MagicMock()
        svc.state_manager.check_event_sequence = MagicMock()

        return svc

    def _setup_cart(self, service, cart_doc: CartDocument):
        """Wire up the private cache/subtotal helpers with the given cart."""
        service._CartService__get_cached_cart_async = AsyncMock(return_value=cart_doc)
        service._CartService__subtotal_async = AsyncMock(return_value=cart_doc)
        service._CartService__cache_cart_async = AsyncMock(return_value=None)

    # ------------------------------------------------------------------ #
    # 正常系                                                               #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_single_item_reduced(self, service):
        """1商品の数量が正しく削減される"""
        item = make_line_item("A001", quantity=5)
        cart = make_cart_doc(item)
        self._setup_cart(service, cart)

        await service.bulk_reduce_line_item_quantity_in_cart_async(
            [{"item_code": "A001", "quantity": 2}]
        )

        assert item.quantity == 3

    @pytest.mark.asyncio
    async def test_multiple_items_reduced(self, service):
        """複数商品が一括で削減される"""
        item_a = make_line_item("A001", quantity=5)
        item_b = make_line_item("B001", quantity=3)
        cart = make_cart_doc(item_a, item_b)
        self._setup_cart(service, cart)

        await service.bulk_reduce_line_item_quantity_in_cart_async(
            [{"item_code": "A001", "quantity": 2}, {"item_code": "B001", "quantity": 1}]
        )

        assert item_a.quantity == 3
        assert item_b.quantity == 2

    @pytest.mark.asyncio
    async def test_reduce_to_zero_is_allowed(self, service):
        """削減後に数量が0になることは許容される"""
        item = make_line_item("A001", quantity=3)
        cart = make_cart_doc(item)
        self._setup_cart(service, cart)

        await service.bulk_reduce_line_item_quantity_in_cart_async(
            [{"item_code": "A001", "quantity": 3}]
        )

        assert item.quantity == 0

    @pytest.mark.asyncio
    async def test_single_cache_read_and_write(self, service):
        """キャッシュの読み書きは各1回のみ"""
        cart = make_cart_doc(make_line_item("A001", quantity=5))
        self._setup_cart(service, cart)

        await service.bulk_reduce_line_item_quantity_in_cart_async(
            [{"item_code": "A001", "quantity": 1}]
        )

        service._CartService__get_cached_cart_async.assert_called_once_with("test-cart-id")
        service._CartService__cache_cart_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_subtotal_called_once(self, service):
        """複数商品削減でも小計再計算は1回のみ"""
        cart = make_cart_doc(
            make_line_item("A001", quantity=5),
            make_line_item("B001", quantity=3),
        )
        self._setup_cart(service, cart)

        await service.bulk_reduce_line_item_quantity_in_cart_async(
            [{"item_code": "A001", "quantity": 1}, {"item_code": "B001", "quantity": 1}]
        )

        service._CartService__subtotal_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_item_ignored_in_active_index(self, service):
        """キャンセル済み行は active_items に含まれない"""
        cancelled = make_line_item("A001", quantity=5, is_cancelled=True)
        active = make_line_item("B001", quantity=3)
        cart = make_cart_doc(cancelled, active)
        self._setup_cart(service, cart)

        # キャンセル済み A001 を指定するとエラー
        with pytest.raises(ItemNotFoundException):
            await service.bulk_reduce_line_item_quantity_in_cart_async(
                [{"item_code": "A001", "quantity": 1}]
            )

    @pytest.mark.asyncio
    async def test_returns_cart_document(self, service):
        """戻り値は CartDocument"""
        cart = make_cart_doc(make_line_item("A001", quantity=5))
        self._setup_cart(service, cart)

        result = await service.bulk_reduce_line_item_quantity_in_cart_async(
            [{"item_code": "A001", "quantity": 1}]
        )

        assert isinstance(result, CartDocument)

    # ------------------------------------------------------------------ #
    # エラー系 — 商品未検出                                                 #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_raises_item_not_found_for_unknown_code(self, service):
        """存在しない item_code は ItemNotFoundException"""
        cart = make_cart_doc(make_line_item("A001", quantity=5))
        self._setup_cart(service, cart)

        with pytest.raises(ItemNotFoundException) as exc_info:
            await service.bulk_reduce_line_item_quantity_in_cart_async(
                [{"item_code": "NOPE", "quantity": 1}]
            )

        assert exc_info.value.error_code == CartErrorCode.ITEM_NOT_FOUND

    @pytest.mark.asyncio
    async def test_raises_item_not_found_error_code(self, service):
        """ItemNotFoundException のエラーコードは 402001"""
        cart = make_cart_doc(make_line_item("A001", quantity=5))
        self._setup_cart(service, cart)

        with pytest.raises(ItemNotFoundException) as exc_info:
            await service.bulk_reduce_line_item_quantity_in_cart_async(
                [{"item_code": "NOPE", "quantity": 1}]
            )

        assert exc_info.value.error_code == "402001"

    # ------------------------------------------------------------------ #
    # エラー系 — 削減数量超過                                               #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_raises_exceeds_when_reduce_qty_greater_than_cart_qty(self, service):
        """削減数量がカート数量を超えると ItemQuantityReductionExceedsException"""
        cart = make_cart_doc(make_line_item("A001", quantity=2))
        self._setup_cart(service, cart)

        with pytest.raises(ItemQuantityReductionExceedsException) as exc_info:
            await service.bulk_reduce_line_item_quantity_in_cart_async(
                [{"item_code": "A001", "quantity": 5}]
            )

        assert exc_info.value.error_code == CartErrorCode.ITEM_QTY_REDUCTION_EXCEEDS

    @pytest.mark.asyncio
    async def test_raises_exceeds_error_code_402006(self, service):
        """ItemQuantityReductionExceedsException のエラーコードは 402006"""
        cart = make_cart_doc(make_line_item("A001", quantity=1))
        self._setup_cart(service, cart)

        with pytest.raises(ItemQuantityReductionExceedsException) as exc_info:
            await service.bulk_reduce_line_item_quantity_in_cart_async(
                [{"item_code": "A001", "quantity": 2}]
            )

        assert exc_info.value.error_code == "402006"

    @pytest.mark.asyncio
    async def test_exact_quantity_reduction_is_allowed(self, service):
        """reduce_qty == current_qty はエラーではない (境界値)"""
        item = make_line_item("A001", quantity=3)
        cart = make_cart_doc(item)
        self._setup_cart(service, cart)

        await service.bulk_reduce_line_item_quantity_in_cart_async(
            [{"item_code": "A001", "quantity": 3}]
        )

        assert item.quantity == 0

    # ------------------------------------------------------------------ #
    # アトミック性 — 一部エラーで全件ロールバック                            #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_atomic_no_update_on_partial_item_not_found(self, service):
        """後続にエラーがある場合、先行する正常商品も変更されない"""
        item_a = make_line_item("A001", quantity=5)
        cart = make_cart_doc(item_a)
        self._setup_cart(service, cart)

        with pytest.raises(ItemNotFoundException):
            await service.bulk_reduce_line_item_quantity_in_cart_async(
                [{"item_code": "A001", "quantity": 1}, {"item_code": "NOPE", "quantity": 1}]
            )

        # A001 は変更されていない
        assert item_a.quantity == 5
        # キャッシュへの書き込みも発生していない
        service._CartService__cache_cart_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_atomic_no_update_on_partial_exceeds(self, service):
        """後続が超過エラーでも、先行する正常商品は変更されない"""
        item_a = make_line_item("A001", quantity=5)
        item_b = make_line_item("B001", quantity=2)
        cart = make_cart_doc(item_a, item_b)
        self._setup_cart(service, cart)

        with pytest.raises(ItemQuantityReductionExceedsException):
            await service.bulk_reduce_line_item_quantity_in_cart_async(
                [{"item_code": "A001", "quantity": 1}, {"item_code": "B001", "quantity": 99}]
            )

        # 両方とも変更されていない
        assert item_a.quantity == 5
        assert item_b.quantity == 2
        service._CartService__cache_cart_async.assert_not_called()

    # ------------------------------------------------------------------ #
    # スキーマバリデーション (BaseBulkQuantityReductionItem)               #
    # ------------------------------------------------------------------ #

    def test_schema_rejects_quantity_zero(self):
        """quantity=0 は Pydantic バリデーションで拒否される"""
        with pytest.raises(Exception) as exc_info:
            BaseBulkQuantityReductionItem(item_code="A001", quantity=0)

        assert "quantity must be greater than 0" in str(exc_info.value)

    def test_schema_rejects_negative_quantity(self):
        """quantity < 0 は Pydantic バリデーションで拒否される"""
        with pytest.raises(Exception) as exc_info:
            BaseBulkQuantityReductionItem(item_code="A001", quantity=-1)

        assert "quantity must be greater than 0" in str(exc_info.value)

    def test_schema_accepts_positive_quantity(self):
        """quantity >= 1 は正常"""
        item = BaseBulkQuantityReductionItem(item_code="A001", quantity=1)
        assert item.quantity == 1

    def test_duplicate_check_raises_on_duplicate_codes(self):
        """重複 item_code があると validate_no_duplicates が ValueError"""
        items = [
            BaseBulkQuantityReductionItem(item_code="A001", quantity=1),
            BaseBulkQuantityReductionItem(item_code="A001", quantity=2),
        ]
        with pytest.raises(ValueError, match="Duplicate item_code"):
            BaseBulkQuantityReductionRequest.validate_no_duplicates(items)

    def test_duplicate_check_passes_for_unique_codes(self):
        """item_code が一意なら validate_no_duplicates は通過する"""
        items = [
            BaseBulkQuantityReductionItem(item_code="A001", quantity=1),
            BaseBulkQuantityReductionItem(item_code="B001", quantity=2),
        ]
        result = BaseBulkQuantityReductionRequest.validate_no_duplicates(items)
        assert result == items

    def test_duplicate_check_passes_for_empty_list(self):
        """空リストは重複なし"""
        result = BaseBulkQuantityReductionRequest.validate_no_duplicates([])
        assert result == []
