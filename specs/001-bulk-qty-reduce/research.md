# Research: 複数商品の一括数量削減API

**Branch**: `001-bulk-qty-reduce` | **Date**: 2026-02-23

## 調査概要

既存のカートサービスコードを調査した結果、全ての疑問点が解決された。

---

## 決定事項

### 1. APIエンドポイントURL設計

**決定**: `PATCH /api/v1/carts/{cart_id}/lineItems/bulkQuantityReduce`

**根拠**:
- 既存パターン `PATCH /carts/{cart_id}/lineItems/{lineNo}/quantity` との一貫性
- `/lineItems/` プレフィックスで明細行操作であることを示す
- `bulkQuantityReduce` はキャメルケースでURL規約に合致
- PATCH は既存カートを部分更新する意味論的に適切なHTTPメソッド

**検討代替案**:
- `POST /carts/{cart_id}/lineItems/bulkQuantityReduce` → POST はリソース作成を示すため不適切
- `PATCH /carts/{cart_id}/bulkQuantityReduce` → lineItems のスコープが不明確
- `PUT /carts/{cart_id}/lineItems/quantities` → PUTは完全置換の意味が強く不適切

---

### 2. 「既存ロジックの再利用」の解釈

**決定**: 新しいサービスメソッド `bulk_reduce_line_item_quantity_in_cart_async` を作成し、その内部でプライベートヘルパー（`__get_cached_cart_async`, `__subtotal_async`, `__cache_cart_async`）を直接利用する

**根拠**:
- 既存 `update_line_item_quantity_in_cart_async` を N 回呼ぶと N 回のキャッシュ読み書きと N 回の小計計算が発生し非効率
- 一括操作はアトミック性が要件（FR-004）のため、1回のキャッシュ操作で完結すべき
- プライベートメソッドを再利用することで「同じロジック」を踏襲しつつバルク最適化を実現
- `update_line_item_quantity_in_cart_async` の処理フロー（get → check state → update → subtotal → cache）は同一のフローを維持

**処理フロー**:
```
1. __get_cached_cart_async(cart_id) → cart_doc 取得（1回）
2. state_manager.check_event_sequence(self) → 状態確認（1回）
3. バリデーションループ（全件、item_code → line_item解決 → 削減数量チェック）
4. 更新ループ（全件、line_item.quantity -= reduction_quantity）
5. __subtotal_async(cart_doc) → 小計再計算（1回）
6. __cache_cart_async(cart_doc, CartStatus.NoUpdate) → キャッシュ保存（1回）
7. return cart_doc
```

---

### 3. item_code → line_no マッピング

**決定**: `cart_doc.line_items` を走査してitem_codeで一致する行を検索する

**根拠**:
- `CartDocument.CartLineItem` は `item_code` と `line_no` 両方を持つ
- データベースアクセス不要（キャッシュから取得済みのcart_docを使用）
- 同一商品コードが複数行に存在する可能性は、バリデーションで事前チェック（重複コードはエラー）

**実装方法**:
```python
line_items_by_code = {
    li.item_code: li
    for li in cart_doc.line_items
    if not li.is_cancelled  # キャンセル済み行は除外
}
```

---

### 4. エラーコード設計

**決定**: 既存の 402xx 商品登録関連エラーに新しいコードを追加

| コード | 定数名 | 説明 |
|--------|--------|------|
| `402006` | `ITEM_QTY_REDUCTION_EXCEEDS` | 削減数量がカート内数量を超えている |

**根拠**:
- 既存コード体系 `402xx` に商品関連エラーが集約されている
- 空リスト・重複コード・ゼロ以下の数量はPydantic バリデーション（422エラー）で処理
- `ItemNotFoundException`（既存 402001）は「カートに存在しない商品コード」エラーに流用可能

**検討代替案**:
- 独立した 405xx 系列を作成 → 既存エラー体系との一貫性が失われるため不採用

---

### 5. アトミック性の実現方法

**決定**: 「バリデーション先行・全件成功時のみ更新実施」パターン

**根拠**:
- インメモリのcart_docを操作しているため、バリデーション後に全更新 → キャッシュ保存という流れで自然にアトミック性が保たれる
- トランザクション機構（DB/Redis）への依存が不要
- 既存パターンとの整合性が高い

**フェール時の動作**:
- バリデーションループでいずれかのアイテムが失敗 → 即時例外送出
- cart_docへの変更は行われない（Pythonのin-memory操作のため）
- キャッシュは更新されない

---

### 6. キャンセル済み行の扱い

**決定**: キャンセル済み行（`is_cancelled=True`）は検索対象から除外する

**根拠**:
- 既存ロジックでキャンセル済み行は数量変更対象外
- `item_code` 検索時にキャンセル済み行がマッチすると不整合が生じる可能性がある
- ユーザーの期待値として「有効な行のみが操作対象」が自然

---

## 調査で確認された既存パターン

### APIルートパターン（cart.py より）

```python
@router.patch(
    "/carts/{cart_id}/lineItems/{lineNo}/quantity",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[Cart],
    responses={
        status.HTTP_400_BAD_REQUEST: StatusCodes.get(status.HTTP_400_BAD_REQUEST),
        status.HTTP_401_UNAUTHORIZED: StatusCodes.get(status.HTTP_401_UNAUTHORIZED),
        status.HTTP_403_FORBIDDEN: StatusCodes.get(status.HTTP_403_FORBIDDEN),
        status.HTTP_404_NOT_FOUND: StatusCodes.get(status.HTTP_404_NOT_FOUND),
        status.HTTP_422_UNPROCESSABLE_ENTITY: StatusCodes.get(status.HTTP_422_UNPROCESSABLE_ENTITY),
        status.HTTP_500_INTERNAL_SERVER_ERROR: StatusCodes.get(status.HTTP_500_INTERNAL_SERVER_ERROR),
    },
)
async def update_item_quantity(...):
    cart_doc = await cart_service.update_line_item_quantity_in_cart_async(lineNo, quantity)
    response = ApiResponse(
        success=True,
        code=status.HTTP_200_OK,
        message=...,
        data=SchemasTransformerV1().transform_cart(cart_doc=cart_doc).model_dump(),
        operation=f"{inspect.currentframe().f_code.co_name}",
    )
    return response
```

### 既存サービスメソッドの処理パターン

```python
async def update_line_item_quantity_in_cart_async(self, line_no: int, quantity: int):
    cart_doc = await self.__get_cached_cart_async(self.cart_id)
    self.state_manager.check_event_sequence(self)
    line_item = cart_doc.line_items[line_no - 1]
    line_item.quantity = quantity
    cart_doc = await self.__subtotal_async(cart_doc)
    await self.__cache_cart_async(cart_doc=cart_doc, cart_status=CartStatus.NoUpdate)
    return cart_doc
```
