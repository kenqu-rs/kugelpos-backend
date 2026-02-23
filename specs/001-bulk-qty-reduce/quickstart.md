# クイックスタート: 複数商品の一括数量削減API

**Branch**: `001-bulk-qty-reduce` | **Date**: 2026-02-23

## APIエンドポイント

```
PATCH /api/v1/carts/{cart_id}/lineItems/bulkQuantityReduce?terminal_id={terminal_id}
```

## 認証

既存のカートAPIと同じ Bearer トークン認証。`Authorization: Bearer {token}` ヘッダーが必要。

## リクエスト例

```bash
curl -X PATCH \
  "http://localhost:8003/api/v1/carts/cart_001/lineItems/bulkQuantityReduce?terminal_id=T001" \
  -H "Authorization: Bearer {your_token}" \
  -H "Content-Type: application/json" \
  -d '[
    {"itemCode": "49-01", "quantity": 2},
    {"itemCode": "49-02", "quantity": 1}
  ]'
```

## 正常レスポンス例（200 OK）

```json
{
  "success": true,
  "code": 200,
  "message": "Bulk quantity reduction completed. cart_id: cart_001",
  "data": {
    "cartId": "cart_001",
    "cartStatus": "EnteringItem",
    "lineItems": [
      {
        "lineNo": 1,
        "itemCode": "49-01",
        "itemName": "商品A",
        "unitPrice": 1000.0,
        "quantity": 3,
        "amount": 3000.0,
        "discounts": [],
        "imageUrls": [],
        "isCancelled": false
      },
      {
        "lineNo": 2,
        "itemCode": "49-02",
        "itemName": "商品B",
        "unitPrice": 500.0,
        "quantity": 1,
        "amount": 500.0,
        "discounts": [],
        "imageUrls": [],
        "isCancelled": false
      }
    ],
    "totalAmount": 3500.0,
    "totalQuantity": 4,
    "subtotalAmount": 3500.0,
    "balanceAmount": 3500.0
  },
  "operation": "bulk_reduce_item_quantity"
}
```

## エラーレスポンス例

### カートに存在しない商品コード（400）

```json
{
  "success": false,
  "code": 400,
  "message": "Item not found: ITEM999",
  "error_code": "402001"
}
```

### 削減数量が登録数量超過（400）

```json
{
  "success": false,
  "code": 400,
  "message": "Reduction quantity exceeds the item quantity in cart: 49-01",
  "error_code": "402006"
}
```

### バリデーションエラー（422）

空リスト・ゼロ以下の数量・重複商品コードの場合：

```json
{
  "detail": [
    {
      "type": "value_error",
      "msg": "List should have at least 1 item after validation",
      "input": []
    }
  ]
}
```

## テスト実行手順

```bash
# サービス起動（別ターミナル）
cd /workspaces/kugelpos-backend
./scripts/start.sh

# テスト実行
cd services/cart
pipenv run pytest tests/test_cart.py -v -k "bulk"
```

## 実装チェックポイント

1. **バリデーション順序**: 全件バリデーション → 全件更新（部分更新しない）
2. **キャンセル済み行の除外**: `is_cancelled=True` の行は検索対象外
3. **アトミック性**: バリデーション通過後のみキャッシュ更新
4. **レスポンス形式**: 既存 `Cart` スキーマをそのまま返す
