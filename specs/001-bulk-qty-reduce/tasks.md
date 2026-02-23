# タスク: 複数商品の一括数量削減API

**Input**: `/specs/001-bulk-qty-reduce/` の設計ドキュメント群
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: ユーザーストーリー別に整理。各ストーリーは独立してテスト・デモ可能。

## Format: `[ID] [P?] [Story?] 説明（ファイルパス）`

- **[P]**: 並行実行可能（異なるファイル、未完了タスクへの依存なし）
- **[Story]**: 対応するユーザーストーリー（US1, US2, US3）
- 各タスクには対象ファイルの絶対パスを含む

---

## Phase 1: Foundational（ブロッキング前提条件）

**Purpose**: US1〜US3 すべてに必要なインフラを先に用意する

**⚠️ CRITICAL**: このフェーズが完了するまでユーザーストーリーの実装を開始しない

- [X] T001 [P] `services/cart/app/exceptions/cart_error_codes.py` に `ITEM_QTY_REDUCTION_EXCEEDS = "402006"` 定数と日英エラーメッセージを追加する
- [X] T002 [P] `services/cart/app/services/cart_service_event.py` に `BULK_REDUCE_LINE_ITEM_QUANTITY_IN_CART = "bulk_reduce_line_item_quantity_in_cart_async"` イベントを追加する
- [X] T003 `services/cart/app/exceptions/cart_exceptions.py` に `ItemQuantityReductionExceedsException`（HTTP 400、エラーコード 402006）クラスを追加する（T001 依存）
- [X] T004 `services/cart/app/exceptions/__init__.py` に `ItemQuantityReductionExceedsException` のエクスポートを追加する（T003 依存）
- [X] T005 `services/cart/app/services/states/entering_item_state.py` の `allowed_events` リストに `ev.BULK_REDUCE_LINE_ITEM_QUANTITY_IN_CART.value` を追加する（T002 依存）

**Checkpoint**: エラーコード・例外・状態機械の基盤が整い、US1〜US3 の実装が開始可能

---

## Phase 2: User Story 1 - 複数商品の一括削減（Priority: P1）🎯 MVP

**Goal**: PATCH エンドポイントで複数商品を一括で数量削減し、更新後のカートを返す

**Independent Test**:
```bash
cd services/cart
pipenv run pytest tests/test_cart.py -v -k "test_bulk_quantity_reduce"
```
カートに複数商品を登録後、一括削減 API を呼び出して数量が正しく減少し 200 OK が返ることを確認する

### US1 実装

- [X] T006 [P] [US1] `services/cart/app/api/common/schemas.py` に `BaseBulkQuantityReductionItem`（item_code, quantity フィールド）と重複 item_code チェックの `@model_validator` を追加する
- [X] T007 [US1] `services/cart/app/api/v1/schemas.py` に `BulkQuantityReductionItem(BaseBulkQuantityReductionItem)` クラスをインポート・追加する（T006 依存）
- [X] T008 [US1] `services/cart/app/services/cart_service.py` に `bulk_reduce_line_item_quantity_in_cart_async(self, reduce_items: list[dict]) -> CartDocument` メソッドを実装する（T004, T005, T006 依存）
- [X] T009 [US1] `services/cart/app/api/v1/cart.py` に `PATCH /carts/{cart_id}/lineItems/bulkQuantityReduce` ルートハンドラ `bulk_reduce_item_quantity` を追加する。service 呼び出し時は `[item.model_dump() for item in reduce_items]` で dict リストに変換する（`add_items` パターン準拠）。スキーマ・サービスをインポートする（T007, T008 依存）
- [X] T010 [US1] `services/cart/tests/test_cart.py` にハッピーパステスト `test_bulk_quantity_reduce`（複数商品の正常削減・数量確認・合計金額確認）を追加する（T009 依存）

**Checkpoint**: US1 完了。カートへの複数商品登録 → 一括削減 → 数量確認の一連フローが動作し単独テスト可能

---

## Phase 3: User Story 2 - 存在しない商品コードのエラー処理（Priority: P2）

**Goal**: カートに存在しない item_code を含むリストを送信した場合、エラーが返りカートが変更されない

**Independent Test**:
```bash
cd services/cart
pipenv run pytest tests/test_cart.py -v -k "test_bulk_quantity_reduce_item_not_found"
```
存在しない item_code を含むリストを送信し、402001 エラーが返りカート内容が変わらないことを確認する

### US2 実装

- [X] T011 [US2] `services/cart/tests/test_cart.py` に存在しない商品コードのエラーテスト `test_bulk_quantity_reduce_item_not_found`（エラーコード 402001 確認、カート変更なし確認）を追加する（T009 依存）

**Checkpoint**: US2 完了。US1 の一括削減 + US2 のエラー処理が独立して動作する

---

## Phase 4: User Story 3 - 削減数量超過のエラー処理（Priority: P3）

**Goal**: 削減数量がカート内登録数量を超える場合、エラーが返りカートが変更されない

**Independent Test**:
```bash
cd services/cart
pipenv run pytest tests/test_cart.py -v -k "test_bulk_quantity_reduce_exceeds"
```
登録数量を超える削減数量を指定し、402006 エラーが返りカート内容が変わらないことを確認する

### US3 実装

- [X] T012 [US3] `services/cart/tests/test_cart.py` に削減数量超過エラーテスト `test_bulk_quantity_reduce_exceeds`（エラーコード 402006 確認、アトミック性確認）を追加する（T009 依存）

**Checkpoint**: US3 完了。US1〜US3 すべてが独立して動作し、エラー系も網羅される

---

## Phase 5: Polish & 横断的関心事

**Purpose**: コード品質の確保とエッジケースのカバレッジ追加

- [X] T013 [P] `services/cart/tests/test_cart.py` にエッジケーステストを追加する: 空リスト→422、重複 item_code→422、quantity=0→422、カートが paying 状態→`EventBadSequenceException` により HTTP 400（状態遷移エラー）、quantity=N を N 個削減して 0 になるケース→200 OK かつ行が残り quantity=0（Assumption A-002 検証）
- [X] T014 [P] `services/cart/` で `pipenv run ruff check --fix app/` と `pipenv run ruff format app/` を実行してコードスタイルを検証する（ruff 未インストールのため flake8 で代替実施、新規追加コードに lint エラーなし）

---

## 依存関係と実行順序

### フェーズ依存関係

```
Phase 1 (Foundational)
  ├── T001 [P] ←───────┐
  ├── T002 [P]          │
  ├── T003 (← T001)     │ 全件完了後に
  ├── T004 (← T003)     │ Phase 2 開始
  └── T005 (← T002)  ───┘

Phase 2 (US1)
  ├── T006 [P] (← Phase1完了)
  ├── T007 (← T006)
  ├── T008 (← T004, T005, T006)
  ├── T009 (← T007, T008)
  └── T010 (← T009)

Phase 3 (US2): T011 (← T009)
Phase 4 (US3): T012 (← T009)
Phase 5 (Polish): T013, T014 (← T009)
```

### ユーザーストーリー依存関係

- **US1 (P1)**: Phase 1 完了後に開始可能。他ストーリーへの依存なし
- **US2 (P2)**: US1 の T009 完了後に開始可能（サービスメソッドが US2 のエラーパスを含む）
- **US3 (P3)**: US1 の T009 完了後に開始可能（サービスメソッドが US3 のエラーパスを含む）

> **注意**: US2・US3 のエラーパス実装は US1 のサービスメソッド（T008）に含まれる。US2/US3 フェーズはテストカバレッジを追加する。

### 並行実行の機会

**Phase 1 内**:
```
並行: T001 と T002（異なるファイル）
↓
順次: T003（← T001）, T005（← T002）
↓
順次: T004（← T003）
```

**Phase 2 内**:
```
並行: T006（← Phase1完了後、すぐ開始可能）
↓
順次: T007（← T006）, T008（← T004, T005, T006）
↓
順次: T009（← T007, T008）
↓
順次: T010（← T009）
```

---

## 並行実行例

### Phase 1 並行実行

```
同時開始:
  Task A: "cart_error_codes.py に ITEM_QTY_REDUCTION_EXCEEDS を追加"  [T001]
  Task B: "cart_service_event.py に BULK_REDUCE_LINE_ITEM_QUANTITY_IN_CART を追加"  [T002]
```

### Phase 5 並行実行

```
同時実行:
  Task A: "エッジケーステストを追加"  [T013]
  Task B: "ruff check/format 実行"  [T014]
```

---

## 実装戦略

### MVP ファースト（US1 のみ）

1. Phase 1 完了（T001〜T005）
2. Phase 2 完了（T006〜T010）
3. **停止・検証**: `pipenv run pytest tests/test_cart.py -v -k "bulk"` で US1 を単独テスト
4. 正常確認後、US2・US3 のエラーパステストを追加

### インクリメンタルデリバリー

1. Phase 1 完了 → 基盤整備
2. Phase 2 完了（T006〜T009）→ API 動作確認（テストなし状態でも curl で確認可能）
3. T010 追加 → 自動テスト有効化 → MVP デモ可能
4. T011 追加 → US2 テスト網羅
5. T012 追加 → US3 テスト網羅
6. T013, T014 → コード品質担保

---

## Notes

- `[P]` タスクは異なるファイルを操作するため安全に並行実行可能
- US2・US3 のテストは US1 サービスメソッド（T008）が既にエラーパスを実装しているため GREEN になるはず
- T008 の `bulk_reduce_line_item_quantity_in_cart_async` は plan.md の擬似コードに従い実装する
- T009 のルートハンドラは `api/v1/cart.py` の既存パターン（`add_items`, `update_item_quantity`）を踏襲する
- 各タスク完了後に `git commit` することを推奨（変更単位が明確）
