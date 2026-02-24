# データモデル: カート内商品数量変更API

**Phase 1 設計** | **日付**: 2026-02-24

---

## 既存エンティティ（変更なし）

### CartDocument
カート全体を表すドキュメント。変更なし。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| cart_id | str | カート識別子 |
| line_items | list[CartLineItem] | 明細行リスト |
| status | CartStatus | カート状態 |
| total_amount | float | 合計金額 |

### CartLineItem（BaseTransaction.LineItem）
各明細行を表す。**変更なし**。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| line_no | int | 行No（1始まり） ← 本APIの検索キー |
| item_code | str | 商品コード |
| quantity | int | 数量 ← 本APIの更新対象 |
| unit_price | float | 単価 |
| amount | float | 金額 |
| is_cancelled | bool | キャンセル済みフラグ |

---

## 新規スキーマ（APIリクエスト用）

### BaseItemLineNoQuantityUpdateRequest
`services/cart/app/api/common/schemas.py` に追加

| フィールド | 型 | バリデーション | 説明 |
|-----------|-----|--------------|------|
| line_no | int | ge=1 | 変更対象の行No |
| quantity | int | ge=1, le=99 | 新しい数量 |

### ItemLineNoQuantityUpdateRequest（v1）
`services/cart/app/api/v1/schemas.py` に追加
`BaseItemLineNoQuantityUpdateRequest` を継承（追加フィールドなし）

---

## バリデーションルール

| ルール | 層 | エラー |
|-------|-----|--------|
| quantity が 1〜99 の範囲内 | Pydantic スキーマ | 422 Unprocessable Entity |
| line_no が 1 以上 | Pydantic スキーマ | 422 Unprocessable Entity |
| line_no がカート内に存在する | サービス層 | 400 Bad Request (402006) |

---

## エラーコード追加

`services/cart/app/exceptions/cart_error_codes.py` に追加

| コード | 定数名 | 説明 |
|--------|--------|------|
| 402006 | LINE_ITEM_NOT_FOUND | 指定した行Noがカートに存在しない |

---

## 状態遷移（変更なし）

新APIは既存の `EnteringItemState` が許可するイベント `UPDATE_LINE_ITEM_QUANTITY_IN_CART` を利用。
ステートマシンへの変更は不要。
