# 実装計画: 複数商品の一括数量削減API

**Branch**: `001-bulk-qty-reduce` | **Date**: 2026-02-23 | **Spec**: [spec.md](./spec.md)

## Summary

カートサービスに一括数量削減エンドポイントを追加する。既存の `update_line_item_quantity_in_cart_async` と同じ処理フロー（キャッシュ取得 → 状態確認 → 更新 → 小計再計算 → キャッシュ保存）を踏襲しつつ、複数商品を1回のリクエストで処理できるようにする。全件バリデーション後に全件更新するアトミック設計を採用。

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI 0.x, Pydantic v2, Motor (async MongoDB), Redis (Dapr State Store), kugel_common
**Storage**: Redis（Dapr State Store経由のカートキャッシュ）, MongoDB（トランザクション永続化）
**Testing**: pytest + pytest-asyncio（既存テストファイル `services/cart/tests/test_cart.py` に追記）
**Target Platform**: Linux サーバー（Docker コンテナ、ポート 8003）
**Performance Goals**: 既存の単件更新 API と同等の応答速度（商品数に対してほぼ線形スケール）
**Constraints**: キャッシュ読み書き・小計計算を各1回に抑えること（N回ループ禁止）
**Scale/Scope**: 1リクエストあたりの商品数は実運用上数件〜数十件を想定（上限なし）

## Constitution Check

*GATE: コーディング前に確認。設計完了後に再確認。*

| チェック項目 | 状態 | 備考 |
|------------|------|------|
| ドキュメントは日本語で記述 | ✅ | plan.md・spec.md・tasks.md は日本語 |
| コード（変数名・関数名）は英語 | ✅ | 実装ファイルはすべて英語 |
| コミットメッセージは英語 | ✅ | Git規約に準拠 |
| 既存パターン・コード規約に従う | ✅ | 既存 `add_items`・`update_item_quantity` のパターンを踏襲 |

## Project Structure

### Documentation (this feature)

```text
specs/001-bulk-qty-reduce/
├── plan.md              # このファイル
├── research.md          # フェーズ0出力（調査・技術決定）
├── data-model.md        # フェーズ1出力（スキーマ・エラーコード定義）
├── quickstart.md        # フェーズ1出力（エンドポイント・curl例）
├── contracts/
│   └── api-contract.yaml  # OpenAPI 3.0 コントラクト
└── tasks.md             # フェーズ2出力（/speckit.tasks コマンドで生成）
```

### Source Code（変更対象ファイル）

```text
services/cart/app/
├── api/
│   ├── common/
│   │   └── schemas.py               # BaseBulkQuantityReductionItem 追加
│   └── v1/
│       ├── schemas.py               # BulkQuantityReductionItem 追加
│       └── cart.py                  # bulk_reduce_item_quantity ルート追加
├── exceptions/
│   ├── cart_error_codes.py          # ITEM_QTY_REDUCTION_EXCEEDS (402006) 追加
│   └── cart_exceptions.py           # ItemQuantityReductionExceedsException 追加
│   └── __init__.py                  # 新例外クラスをエクスポート
└── services/
    ├── cart_service.py              # bulk_reduce_line_item_quantity_in_cart_async 追加
    ├── cart_service_event.py        # BULK_REDUCE_LINE_ITEM_QUANTITY_IN_CART 追加
    └── states/
        └── entering_item_state.py   # 新イベントを allowed_events に追加

services/cart/tests/
└── test_cart.py                     # バルク削減テストケース追加
```

**Structure Decision**: 既存の単一プロジェクト構成（`services/cart/`）に変更を加える。新ファイルは作成せず、既存ファイルへの追記のみ。

## 設計詳細

### 1. APIエンドポイント

```
PATCH /api/v1/carts/{cart_id}/lineItems/bulkQuantityReduce?terminal_id={terminal_id}
```

- HTTPメソッド: **PATCH**（既存 `lineItems/{lineNo}/quantity` と一貫）
- レスポンス: `200 OK`, `ApiResponse[Cart]`
- 認証: 既存 `get_cart_service_with_cart_id_async` Depends を使用

### 2. リクエストスキーマ

```python
# common/schemas.py
class BaseBulkQuantityReductionItem(BaseSchemmaModel):
    item_code: str          # camelCase: itemCode
    quantity: int           # 削減数量（1以上）

# v1/schemas.py
class BulkQuantityReductionItem(BaseBulkQuantityReductionItem):
    pass
```

リクエストボディ: `list[BulkQuantityReductionItem]`（`add_items` と同形式）

Pydanticバリデーション（422エラー）:
- リスト最低1件（`min_length=1`）
- `quantity >= 1`
- `item_code` 重複チェック（`@model_validator`）

### 3. サービスメソッド

```python
async def bulk_reduce_line_item_quantity_in_cart_async(
    self, reduce_items: list[dict]
) -> CartDocument:
    """
    複数商品の数量を一括削減する。
    全件バリデーション通過後にのみ更新を実施（アトミック操作）。
    """
    # 1. キャッシュから取得（1回）
    cart_doc = await self.__get_cached_cart_async(self.cart_id)

    # 2. 状態確認（メソッド名から自動検出）
    self.state_manager.check_event_sequence(self)

    # 3. アクティブ行のitem_codeインデックス作成
    active_items = {
        li.item_code: li
        for li in cart_doc.line_items
        if not li.is_cancelled
    }

    # 4. 全件バリデーション（例外が出たら即終了・更新なし）
    for item in reduce_items:
        item_code = item["item_code"]
        reduce_qty = item["quantity"]
        if item_code not in active_items:
            raise ItemNotFoundException(f"Item not found: {item_code}", logger)
        if reduce_qty > active_items[item_code].quantity:
            raise ItemQuantityReductionExceedsException(
                f"Reduction quantity exceeds the item quantity in cart: {item_code}", logger
            )

    # 5. 全件更新（インメモリ）
    for item in reduce_items:
        active_items[item["item_code"]].quantity -= item["quantity"]

    # 6. 小計再計算（1回）
    cart_doc = await self.__subtotal_async(cart_doc)

    # 7. キャッシュ保存（1回）
    await self.__cache_cart_async(cart_doc=cart_doc, cart_status=CartStatus.NoUpdate)

    return cart_doc
```

### 4. 状態機械への登録

```python
# cart_service_event.py
BULK_REDUCE_LINE_ITEM_QUANTITY_IN_CART = "bulk_reduce_line_item_quantity_in_cart_async"

# entering_item_state.py の allowed_events に追加
ev.BULK_REDUCE_LINE_ITEM_QUANTITY_IN_CART.value,
```

### 5. エラーコード・例外

| コード | 定数 | 例外クラス | HTTP | 発生条件 |
|--------|------|-----------|------|---------|
| `402001` | `ITEM_NOT_FOUND` | `ItemNotFoundException`（既存） | 404 | item_codeがカートに存在しない |
| `402006` | `ITEM_QTY_REDUCTION_EXCEEDS` | `ItemQuantityReductionExceedsException`（新規） | 400 | 削減数量がカート内登録数量を超える |

## 実装順序

実装は以下の順序で行う（後段が前段に依存するため）:

1. エラーコード追加（`cart_error_codes.py`）
2. 例外クラス追加（`cart_exceptions.py`, `__init__.py`）
3. イベント追加（`cart_service_event.py`）
4. 状態機械更新（`entering_item_state.py`）
5. スキーマ追加（`common/schemas.py`, `v1/schemas.py`）
6. サービスメソッド追加（`cart_service.py`）
7. ルートハンドラ追加（`api/v1/cart.py`）
8. テスト追加（`tests/test_cart.py`）

## 制約・注意事項

- `__get_cached_cart_async` / `__subtotal_async` / `__cache_cart_async` は `CartService` の private メソッド。同クラス内からのみ呼び出し可能（名前マングリング）
- 同一 `item_code` が複数のアクティブ行に存在する場合、最初のマッチ行を採用（辞書内包表記の順序保証）
- `item_code` 重複チェックは Pydantic `@model_validator` で実装し HTTP 422 を返す
- 既存の `add_items` ルートが `list[Item]` をボディに取るパターンと同様、ラッパーオブジェクト不要
- **FR-006「既存ロジック再利用」の解釈**: `update_line_item_quantity_in_cart_async` を N 回呼ぶのではなく、同メソッドが内部で使う private ヘルパー群（`__get_cached_cart_async` / `__subtotal_async` / `__cache_cart_async`）を直接利用することで「ロジックの再利用」を実現する。N 回呼び出しはアトミック性（FR-004）と効率（Constraints）に反するため採用しない（詳細は research.md §2 参照）
