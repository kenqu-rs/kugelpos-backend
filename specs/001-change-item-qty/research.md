# Research: カート内商品数量変更API

**Phase 0 調査結果** | **日付**: 2026-02-24

---

## 調査対象

### 1. 既存の数量変更API（再利用元）

**Decision**: 既存の `update_line_item_quantity_in_cart_async` メソッドを直接再利用する

**調査結果**:
- 既存エンドポイント: `PATCH /carts/{cart_id}/lineItems/{lineNo}/quantity`（lineNo はパスパラメーター）
- サービスメソッド: `update_line_item_quantity_in_cart_async(line_no: int, quantity: int) -> CartDocument`
- 現在の実装: `cart_doc.line_items[line_no - 1]` で直接配列アクセス
- バリデーションなし: 範囲外 line_no は IndexError になる

**Rationale**: 既存ロジックを維持し、新しいエンドポイントから呼び出すことで一貫性を保つ

**Alternatives considered**:
- 別の新しいサービスメソッドを作成 → 不要な重複。spec 要件「既存ロジック再利用」に反する

---

### 2. APIエンドポイント設計

**Decision**: `PATCH /carts/{cart_id}/lineItems/quantity` でリクエストボディに `line_no` を含める

**調査結果**:
- 既存エンドポイントはパスパラメーターで lineNo を受け取る
- 新エンドポイントはボディに `{"line_no": 1, "quantity": 2}` を受け取る（spec要件）
- 既存パターン（`add_items`）でも複数商品はボディで受け取る

**Rationale**: spec 要件の通りリクエストボディに行Noを含める設計。URLの衝突を回避できる

**Alternatives considered**:
- 既存エンドポイントの拡張 → パスパラメーターとボディパラメーターの混在で設計が不一致になる

---

### 3. バリデーション方針

**Decision**: Pydantic スキーマ（数量範囲）+ サービス層（行No存在チェック）で二層バリデーション

**調査結果**:
- `BaseItemQuantityUpdateRequest` に数量バリデーションなし（現状）
- `cart_doc.line_items[line_no - 1]` での直接アクセスは IndexError リスクあり
- Pydantic の `Field(ge=1, le=99)` で範囲チェックが自然

**Rationale**:
- 数量範囲 (1〜99): スキーマレベルで弾く → 422 Unprocessable Entity
- 行No存在確認: サービス層で `len(cart_doc.line_items)` と比較 → 400 Bad Request

**Alternatives considered**:
- APIレイヤーだけでバリデーション → サービス層の IndexError が防げず非安全

---

### 4. エラーコード設計

**Decision**: 既存の 402xx 系に追加（商品登録関連）

**調査結果**:
- 既存: `ITEM_NOT_FOUND = "402001"` 〜 `DISCOUNT_RESTRICTION = "402005"`
- 新規追加: `LINE_ITEM_NOT_FOUND = "402006"`

**Rationale**: 行No不存在は商品登録関連エラーと分類が同じ。既存体系に自然に追加できる

**Note**: 数量範囲エラーは Pydantic バリデーションで 422 として返すため、独自エラーコード不要

---

### 5. ステートマシン連携

**Decision**: 既存の `UPDATE_LINE_ITEM_QUANTITY_IN_CART` イベントをそのまま利用

**調査結果**:
- `CartServiceEvent.UPDATE_LINE_ITEM_QUANTITY_IN_CART = "update_line_item_quantity_in_cart_async"`
- `EnteringItemState` の許可イベントリストに既に含まれている
- `check_event_sequence` は呼び出し元メソッド名を自動検出する仕組み

**Rationale**: 既存サービスメソッドを再利用するため、ステートチェックは自動的に通過する

---

## 結論サマリー

| 項目 | 決定内容 |
|------|---------|
| APIパス | `PATCH /carts/{cart_id}/lineItems/quantity` |
| リクエスト | `{"line_no": int, "quantity": int(1-99)}` |
| 数量バリデーション | Pydantic Field(ge=1, le=99) → 422 |
| 行No バリデーション | サービス層で存在チェック → 400 + 402006 |
| 再利用メソッド | `update_line_item_quantity_in_cart_async` |
| 新規エラーコード | `LINE_ITEM_NOT_FOUND = "402006"` |
