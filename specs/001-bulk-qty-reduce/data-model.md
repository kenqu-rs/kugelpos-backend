# データモデル: 複数商品の一括数量削減API

**Branch**: `001-bulk-qty-reduce` | **Date**: 2026-02-23

## 新規追加エンティティ

### BulkQuantityReductionItem（一括削減リクエストの1件）

| フィールド | 型 | 必須 | バリデーション | 説明 |
|-----------|-----|------|---------------|------|
| `item_code` | `str` | ✅ | 空文字不可 | 削減対象の商品コード |
| `quantity` | `int` | ✅ | `> 0` | 削減する数量（減算値） |

**JSONキー（camelCase）**: `itemCode`, `quantity`

---

### BulkQuantityReductionRequest（リクエスト全体）

| フィールド | 型 | 必須 | バリデーション | 説明 |
|-----------|-----|------|---------------|------|
| `items` | `list[BulkQuantityReductionItem]` | ✅ | 最低1件、重複item_code不可 | 削減する商品と数量のリスト |

**注意**: リクエストボディはリスト形式（`list[BulkQuantityReductionItem]`）で受け取る。
既存の `lineItems` エンドポイントが `list[Item]` を直接受け取る形式と統一。

---

## 既存エンティティへの変更

### CartErrorCode（追加）

| 定数名 | エラーコード | 説明 |
|--------|-------------|------|
| `ITEM_QTY_REDUCTION_EXCEEDS` | `"402006"` | 削減数量がカート内登録数量を超えている |

### CartErrorMessage（追加）

| 言語 | エラーコード | メッセージ |
|------|-------------|-----------|
| `ja` | `402006` | `削減数量がカート内の商品数量を超えています` |
| `en` | `402006` | `Reduction quantity exceeds the item quantity in cart` |

### cart_exceptions.py（追加クラス）

```
ItemQuantityReductionExceedsException
  └── CartErrorCode.ITEM_QTY_REDUCTION_EXCEEDS (402006)
  └── HTTP 400 Bad Request
```

---

## 既存エンティティ（参照のみ・変更なし）

### CartDocument.CartLineItem

カートの各明細行（既存）。バルク削減操作時に参照・更新される。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `line_no` | `int` | 行番号（1-indexed） |
| `item_code` | `str` | 商品コード（検索キー） |
| `quantity` | `int` | 現在の数量（削減対象） |
| `is_cancelled` | `bool` | キャンセル済みフラグ（`True`の行は操作対象外） |
| `amount` | `float` | 小計（subtotal再計算で更新） |

### Cart（レスポンス）

既存の `Cart` スキーマをそのまま返却。変更なし。

---

## 配置ファイルマッピング

| エンティティ | ファイルパス |
|-------------|-------------|
| `BulkQuantityReductionItem` | `services/cart/app/api/common/schemas.py`（BaseクラスとしてBaseBulkQuantityReductionItem） |
| `BulkQuantityReductionItem`（v1） | `services/cart/app/api/v1/schemas.py` |
| `ITEM_QTY_REDUCTION_EXCEEDS` | `services/cart/app/exceptions/cart_error_codes.py` |
| `ItemQuantityReductionExceedsException` | `services/cart/app/exceptions/cart_exceptions.py` |
| `bulk_reduce_line_item_quantity_in_cart_async` | `services/cart/app/services/cart_service.py` |
| ルートハンドラ `bulk_reduce_item_quantity` | `services/cart/app/api/v1/cart.py` |
| テスト | `services/cart/tests/test_cart.py` |
