# API コントラクト: カート内商品数量変更

**作成日**: 2026-02-24

---

## 新規エンドポイント

### PATCH /api/v1/carts/{cart_id}/lineItems/quantity

カートに登録済みの商品の数量を行Noで指定して変更する。

#### パスパラメーター

| パラメーター | 型 | 必須 | 説明 |
|------------|-----|------|------|
| cart_id | string | ✅ | カート識別子 |

#### リクエストヘッダー

| ヘッダー | 必須 | 説明 |
|---------|------|------|
| X-API-Key | ✅ | ターミナルAPIキー |
| Content-Type | ✅ | `application/json` |

#### リクエストボディ

```json
{
  "line_no": 1,
  "quantity": 3
}
```

| フィールド | 型 | 必須 | バリデーション | 説明 |
|-----------|-----|------|--------------|------|
| line_no | integer | ✅ | ge=1 | 変更対象の行No |
| quantity | integer | ✅ | ge=1, le=99 | 新しい数量 |

#### レスポンス（成功）

**HTTP 200 OK**

```json
{
  "success": true,
  "code": 200,
  "message": "Quantity updated. cart_id: {cart_id}, line_no: {line_no}",
  "data": {
    "cart_id": "...",
    "line_items": [
      {
        "line_no": 1,
        "item_code": "A001",
        "quantity": 3,
        "unit_price": 100.0,
        "amount": 300.0
      }
    ],
    "total_amount": 300.0
  },
  "operation": "change_item_quantity"
}
```

#### レスポンス（エラー）

| HTTPステータス | エラーコード | 発生条件 |
|--------------|------------|---------|
| 400 Bad Request | 402006 | 指定した line_no がカートに存在しない |
| 401 Unauthorized | - | APIキーが無効 |
| 403 Forbidden | - | アクセス権限なし |
| 404 Not Found | 401002 | cart_id が存在しない |
| 422 Unprocessable Entity | - | line_no < 1、quantity < 1 または quantity > 99 |
| 500 Internal Server Error | 404004 | 内部処理エラー |

---

## 既存エンドポイント（変更なし）

### PATCH /api/v1/carts/{cart_id}/lineItems/{lineNo}/quantity
既存エンドポイント。lineNo をパスパラメーターで受け取る。変更なし。

---

## 変更一覧

| 種別 | 対象 | 内容 |
|------|------|------|
| 追加 | エンドポイント | `PATCH /carts/{cart_id}/lineItems/quantity` |
| 追加 | スキーマ | `BaseItemLineNoQuantityUpdateRequest` |
| 追加 | スキーマ | `ItemLineNoQuantityUpdateRequest` |
| 追加 | エラーコード | `LINE_ITEM_NOT_FOUND = "402006"` |
| 修正 | サービス | `update_line_item_quantity_in_cart_async` に line_no 存在チェック追加 |
