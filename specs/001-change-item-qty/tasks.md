# Tasks: カート内商品数量変更API

**Input**: Design documents from `/specs/001-change-item-qty/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: タスクはユーザーストーリー単位でグループ化。各ストーリーは独立してテスト可能。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能（異なるファイル、依存関係なし）
- **[Story]**: 対応するユーザーストーリー（US1〜US4）
- 全タスクに正確なファイルパスを記載

## Path Conventions

- サービス本体: `services/cart/app/`
- テスト: `services/cart/tests/`

---

## Phase 1: Setup（環境確認）

**Purpose**: 既存コードのパターンを確認し、実装の前提を整える

- [x] T001 既存の `services/cart/tests/test_cart.py` を読み、テストの構造・フィクスチャ・assertパターンを確認する
- [x] T002 既存の `services/cart/app/api/v1/cart.py` を読み、エンドポイント定義パターン（@router.patch, response_model, Depends）を確認する

---

## Phase 2: Foundational（全ストーリー共通の基盤）

**Purpose**: 全ユーザーストーリーの実装に必要な共通コンポーネント。このフェーズ完了前に各ストーリーの実装を開始してはならない

**⚠️ CRITICAL**: Phase 2 完了前はいかなるストーリー実装も開始不可

- [x] T003 `services/cart/app/exceptions/cart_error_codes.py` の `CartErrorCode` クラスに `LINE_ITEM_NOT_FOUND = "402006"` を追加する
- [x] T004 `services/cart/app/exceptions/cart_error_codes.py` の `CartErrorMessage.MESSAGES` に ja: `"指定した行Noの商品が見つかりません"` / en: `"Line item not found"` を追加する
- [x] T005 [P] `services/cart/app/api/common/schemas.py` に `BaseItemLineNoQuantityUpdateRequest(BaseSchemmaModel)` クラスを追加する（フィールド: `line_no: int = Field(ge=1)`, `quantity: int = Field(ge=1, le=99)`）
- [x] T006 [P] `services/cart/app/api/v1/schemas.py` に `ItemLineNoQuantityUpdateRequest(BaseItemLineNoQuantityUpdateRequest)` クラスを追加する（pass のみ、v1 継承パターン準拠）

**Checkpoint**: エラーコードとスキーマが揃い、ストーリー実装を開始可能

---

## Phase 3: User Story 1 - 正常な数量変更 (Priority: P1) 🎯 MVP

**Goal**: 行Noと数量を指定して、カート内の商品数量を正常に更新できる

**Independent Test**: カートに商品を1件登録し `PATCH /carts/{cart_id}/lineItems/quantity` に `{"line_no": 1, "quantity": 3}` を送信 → レスポンスの line_items[0].quantity が 3 になっていることを確認

### Implementation for User Story 1

- [x] T007 [US1] `services/cart/app/api/v1/cart.py` に `change_item_quantity` 関数を追加する（`@router.patch("/carts/{cart_id}/lineItems/quantity")`, `response_model=ApiResponse[Cart]`, `Depends(get_cart_service_with_cart_id_async)` を使用）
- [x] T008 [US1] `services/cart/app/api/v1/cart.py` の `change_item_quantity` 内で `cart_service.update_line_item_quantity_in_cart_async(line_no, quantity)` を呼び出し、`ApiResponse` で返す処理を実装する（既存 `update_item_quantity` のパターンに準拠）
- [x] T009 [US1] `services/cart/tests/test_change_item_qty.py` を新規作成し、正常系テストを実装する（カート作成→商品追加→数量変更→レスポンスの quantity 検証）
- [x] T019 [P] [US1] `services/cart/tests/test_change_item_qty.py` に、複数商品カートで指定行のみ更新されることを確認するテストを追加する（商品A・Bを登録 → 行No 1 のみ変更 → 行No 1 の quantity が変わり行No 2 は変わらないことを検証）（spec.md US1 Acceptance Scenario 2 対応）
- [x] T020 [P] [US1] `services/cart/tests/test_change_item_qty.py` に、entering_item 以外の状態（例: paying）でリクエストした場合にエラーが返ることを確認するテストを追加する（FR-006 対応）

**Checkpoint**: `test_change_item_qty.py` の正常系テストが通れば US1 完了

---

## Phase 4: User Story 2 & 4 - 行Noバリデーション (Priority: P2)

**Goal**: 存在しない行Noやキャンセル済みの行Noを指定した場合に、適切なエラー（402006）を返す

**Independent Test**: 存在しない line_no=999 を指定 → 400 + エラーコード `402006` が返る。キャンセル済み行の line_no を指定 → 同様に 400 + `402006` が返る

### Implementation for User Story 2 & 4

- [x] T010 [US2] `services/cart/app/services/cart_service.py` の `update_line_item_quantity_in_cart_async` に、`cart_doc.line_items[line_no - 1]` アクセスの前に行No範囲チェックを追加する（`line_no < 1 or line_no > len(cart_doc.line_items)` の場合 `CartErrorCode.LINE_ITEM_NOT_FOUND` でエラーを raise）※実装前に `services/cart/app/exceptions/cart_exceptions.py` と既存の `cancel_line_item_from_cart_async` を参照して正しい例外クラスを確認すること
- [x] T011 [US4] `services/cart/app/services/cart_service.py` の `update_line_item_quantity_in_cart_async` に、行No範囲チェックの直後に `is_cancelled` チェックを追加する（`line_item.is_cancelled is True` の場合 `CartErrorCode.LINE_ITEM_NOT_FOUND` で同一エラーを raise）
- [x] T012 [P] [US2] `services/cart/tests/test_change_item_qty.py` に、存在しない line_no を指定した場合のエラーテストを追加する（`line_no=999` → ステータス 400、エラーコード `402006`）
- [x] T013 [P] [US4] `services/cart/tests/test_change_item_qty.py` に、キャンセル済み行Noを指定した場合のエラーテストを追加する（明細をキャンセル後 → 同行Noに数量変更 → ステータス 400、エラーコード `402006`）

**Checkpoint**: US2+US4 のエラーテストが通り、US1 の正常系も引き続き通ること

---

## Phase 5: User Story 3 - 数量範囲バリデーション (Priority: P3)

**Goal**: 数量が 1 未満または 99 超の値を指定した場合に 422 Unprocessable Entity が返る

**Independent Test**: `quantity=100` を指定 → 422 が返る。`quantity=0` を指定 → 422 が返る。`quantity=99` を指定 → 200 が返る（境界値）

**Note**: このバリデーションは T005/T006 で追加した Pydantic スキーマ（`Field(ge=1, le=99)`）により自動処理される。追加の実装コードは不要

### Implementation for User Story 3

- [x] T014 [P] [US3] `services/cart/tests/test_change_item_qty.py` に、`quantity=100`（上限超過）で 422 が返るテストを追加する
- [x] T015 [P] [US3] `services/cart/tests/test_change_item_qty.py` に、`quantity=0`（下限未満）で 422 が返るテストを追加する
- [x] T016 [P] [US3] `services/cart/tests/test_change_item_qty.py` に、`quantity=99`（境界値・正常）で 200 が返るテストを追加する

**Checkpoint**: 全4ストーリーのテストが通ること

---

## Phase 6: Polish & 横断的品質確認

**Purpose**: 全ストーリー完了後の品質チェックとリグレッション確認

- [x] T017 [P] `services/cart/app/exceptions/cart_error_codes.py`, `app/api/common/schemas.py`, `app/api/v1/schemas.py`, `app/api/v1/cart.py`, `app/services/cart_service.py` に対して `ruff check` を実行し、警告・エラーを修正する
- [x] T018 [P] 既存の `services/cart/tests/test_cart.py` を実行し、リグレッションがないことを確認する（既存の数量変更テスト `update_item_quantity` が引き続き通ること）

---

## Dependencies & Execution Order

### フェーズ依存関係

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ← 全ストーリーをブロック
    ↓
Phase 3 (US1 - P1) ← MVP
    ↓
Phase 4 (US2+US4 - P2)
    ↓
Phase 5 (US3 - P3)
    ↓
Phase 6 (Polish)
```

### ユーザーストーリー依存関係

- **US1 (P1)**: Phase 2 完了後に開始可能。他ストーリーへの依存なし
- **US2+US4 (P2)**: Phase 2 完了後に開始可能（US1 実装完了後を推奨。同一サービスメソッドへの変更のため）
- **US3 (P3)**: Phase 2 完了後に開始可能（スキーマのみで完結、他ストーリーへの依存なし）

### 各ストーリー内の順序

- Foundational（スキーマ・エラーコード）→ 実装 → テスト
- サービス変更（T010, T011）は順番通り実行（T010 → T011、同一メソッド内）
- テスト（T012, T013）は並列実行可能 [P]

### 並列実行の機会

- T005, T006（スキーマ追加）: 異なるファイルのため並列可能
- T009, T019, T020（US1 テスト追加）: 並列可能（同一ファイルへの追記だが独立したテスト関数）
- T012, T013（US2+US4 テスト追加）: 異なるシナリオのため並列可能
- T014, T015, T016（US3 テスト）: 並列可能
- T017, T018（Polish）: 並列可能

---

## Parallel Example: Phase 2

```bash
# Phase 2 のスキーマ追加は並列実行可能:
Task: T005 - BaseItemLineNoQuantityUpdateRequest を common/schemas.py に追加
Task: T006 - ItemLineNoQuantityUpdateRequest を v1/schemas.py に追加
```

---

## Implementation Strategy

### MVP（US1 のみ）

1. Phase 1: Setup（T001-T002）
2. Phase 2: Foundational（T003-T006）
3. Phase 3: US1（T007-T009）
4. **STOP & VALIDATE**: `pytest tests/test_change_item_qty.py::test_*正常系*` が通ることを確認
5. デモ可能な状態

### インクリメンタル配信

1. Phase 1+2 → 基盤完成
2. Phase 3（US1）→ 正常系エンドポイント完成 → デモ（MVP!）
3. Phase 4（US2+US4）→ エラーハンドリング完成
4. Phase 5（US3）→ 範囲バリデーション完成（スキーマで自動対応）
5. Phase 6（Polish）→ 品質確認

---

## Notes

- [P] タスク = 異なるファイル、依存関係なし
- [Story] ラベルはトレーサビリティのためにユーザーストーリーと紐付け
- US3 の数量バリデーションは Pydantic スキーマで自動処理されるため実装コードなし
- `update_item_quantity`（既存エンドポイント）への変更は不要。`update_line_item_quantity_in_cart_async` のバリデーション追加（T010, T011）は両エンドポイントを保護する
- テスト実行順: conftest.py に従い `test_clean_data.py` → `test_setup_data.py` → `test_change_item_qty.py`
