# 実装計画: カート内商品数量変更API

**Branch**: `001-change-item-qty` | **Date**: 2026-02-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-change-item-qty/spec.md`

---

## サマリー

カートに登録済みの商品の数量を、行No（line_no）とリクエストボディで変更する新しいAPIエンドポイントを追加する。
既存の `update_line_item_quantity_in_cart_async` メソッドを再利用し、行No存在チェックと数量範囲バリデーション（1〜99）を追加する。

---

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI, Pydantic v2, Motor (async MongoDB), kugel_common, Dapr State Store (Redis)
**Storage**: Redis（Dapr State Store 経由のカートキャッシュ）, MongoDB（トランザクション永続化）
**Testing**: pytest, pytest-asyncio
**Target Platform**: Linux サーバー（Docker コンテナ）
**Project Type**: マイクロサービス（cartサービス単体）
**Performance Goals**: 既存APIと同等（通常の FastAPI エンドポイント性能）
**Constraints**: 既存 cartサービスの APIパターン・コード規約に完全準拠
**Scale/Scope**: cartサービス単体への最小限の変更

---

## Constitution Check

### 言語ポリシー確認

| 対象 | 言語 | 準拠 |
|------|------|------|
| 変数名・関数名・クラス名 | 英語 | ✅ |
| ファイル名 | 英語 | ✅ |
| コード内コメント | 日本語 | ✅ |
| 本ドキュメント（plan.md） | 日本語 | ✅ |

**Gate**: 全項目準拠 → PASS

---

## Project Structure

### Documentation (this feature)

```text
specs/001-change-item-qty/
├── plan.md              # 本ファイル
├── research.md          # Phase 0 調査結果
├── data-model.md        # Phase 1 データモデル設計
├── contracts/
│   └── api-contract.md  # APIコントラクト
└── tasks.md             # Phase 2 タスク一覧（/speckit.tasks で生成）
```

### Source Code（変更対象ファイル）

```text
services/cart/
├── app/
│   ├── api/
│   │   ├── common/
│   │   │   └── schemas.py          # [追加] BaseItemLineNoQuantityUpdateRequest
│   │   └── v1/
│   │       ├── schemas.py          # [追加] ItemLineNoQuantityUpdateRequest
│   │       └── cart.py             # [追加] change_item_quantity エンドポイント
│   ├── services/
│   │   └── cart_service.py         # [修正] update_line_item_quantity_in_cart_async に line_no バリデーション追加
│   └── exceptions/
│       └── cart_error_codes.py     # [追加] LINE_ITEM_NOT_FOUND エラーコード
└── tests/
    └── test_change_item_qty.py     # [新規] 新エンドポイントのテスト
```

**Structure Decision**: 既存のcartサービス内にのみ変更を加える。新規ファイルの作成は最小限（テストファイルのみ）。

---

## 実装フェーズ

### Phase 1: エラーコード追加

**対象**: `services/cart/app/exceptions/cart_error_codes.py`

`CartErrorCode` クラスに以下を追加:
```python
LINE_ITEM_NOT_FOUND = "402006"  # 指定した行Noがカートに存在しない
```

`CartErrorMessage.MESSAGES` に日英メッセージを追加:
- ja: `"指定した行Noの商品が見つかりません"`
- en: `"Line item not found"`

---

### Phase 2: リクエストスキーマ追加

**対象**: `services/cart/app/api/common/schemas.py`

```python
class BaseItemLineNoQuantityUpdateRequest(BaseSchemmaModel):
    """行Noと数量を指定して数量変更するリクエストモデル"""
    line_no: int = Field(ge=1, description="変更対象の行No")
    quantity: int = Field(ge=1, le=99, description="新しい数量")
```

**対象**: `services/cart/app/api/v1/schemas.py`

```python
class ItemLineNoQuantityUpdateRequest(BaseItemLineNoQuantityUpdateRequest):
    """API v1 版：行Noと数量を指定して数量変更するリクエストモデル"""
    pass
```

---

### Phase 3: サービス層バリデーション追加

**対象**: `services/cart/app/services/cart_service.py`
**メソッド**: `update_line_item_quantity_in_cart_async`

`cart_doc.line_items[line_no - 1]` の直前に以下を追加:
```python
# line_no の存在チェック（1始まり、キャンセル済み行も含む全行数で検証）
if line_no < 1 or line_no > len(cart_doc.line_items):
    raise AppException(
        error_code=CartErrorCode.LINE_ITEM_NOT_FOUND,
        message=CartErrorMessage.get_message(CartErrorCode.LINE_ITEM_NOT_FOUND),
        logger=logger,
    )
```

**補足**: この変更により既存の `update_item_quantity` エンドポイントも IndexError から保護される。

---

### Phase 4: 新規APIエンドポイント追加

**対象**: `services/cart/app/api/v1/cart.py`

```python
@router.patch(
    "/carts/{cart_id}/lineItems/quantity",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[Cart],
    responses={...},  # 既存エンドポイントと同じレスポンスコード定義
)
async def change_item_quantity(
    quantity_update: ItemLineNoQuantityUpdateRequest,
    cart_service: CartService = Depends(get_cart_service_with_cart_id_async),
):
    """行Noを指定してカート内商品の数量を変更する"""
    cart_id = cart_service.cart_id
    line_no = quantity_update.line_no
    quantity = quantity_update.quantity
    cart_doc = await cart_service.update_line_item_quantity_in_cart_async(line_no, quantity)
    response = ApiResponse(
        success=True,
        code=status.HTTP_200_OK,
        message=f"Quantity updated. cart_id: {cart_id}, line_no: {line_no}",
        data=SchemasTransformerV1().transform_cart(cart_doc=cart_doc).model_dump(),
        operation=f"{inspect.currentframe().f_code.co_name}",
    )
    return response
```

**重要**: URL `/carts/{cart_id}/lineItems/quantity` は FastAPI のルーティング上、`/carts/{cart_id}/lineItems/{lineNo}/quantity` とは別ルートとして登録される（衝突なし）。

---

### Phase 5: テスト追加

**対象**: `services/cart/tests/test_change_item_qty.py`

テストケース:
1. 正常: 有効な line_no と quantity で数量が更新される
2. 正常: 複数商品カートで指定行のみ更新される
3. 異常: 存在しない line_no → 400 + エラーコード 402006
4. 異常: quantity = 100（上限超過）→ 422
5. 異常: quantity = 0（下限未満）→ 422

---

## Complexity Tracking

変更は既存パターンへの最小限の追加のみ。Constitution 違反なし。

---

## 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `app/exceptions/cart_error_codes.py` | 修正 | エラーコード・メッセージ追加 |
| `app/api/common/schemas.py` | 修正 | BaseItemLineNoQuantityUpdateRequest 追加 |
| `app/api/v1/schemas.py` | 修正 | ItemLineNoQuantityUpdateRequest 追加 |
| `app/services/cart_service.py` | 修正 | line_no 存在バリデーション追加 |
| `app/api/v1/cart.py` | 修正 | change_item_quantity エンドポイント追加 |
| `tests/test_change_item_qty.py` | 新規 | テスト追加 |
