# イベントシーケンス図: 複数商品の一括数量削減API

## 1. 正常系フロー (200 OK)

```mermaid
sequenceDiagram
    autonumber
    participant Client as クライアント
    participant FastAPI as FastAPI<br/>(Pydantic検証)
    participant Dep as Dependency<br/>get_cart_service_with_cart_id_async
    participant TerminalAuth as TerminalAuth<br/>(API Key認証)
    participant Router as RouteHandler<br/>bulk_reduce_item_quantity
    participant Service as CartService<br/>bulk_reduce_line_item_quantity_in_cart_async
    participant State as CartStateManager<br/>/ EnteringItemState
    participant Redis as Redis<br/>(Dapr State Store)
    participant Subtotal as calc_subtotal_logic
    participant Transformer as SchemasTransformerV1

    Client->>FastAPI: PATCH /api/v1/carts/{cart_id}/lineItems/bulkQuantityReduce<br/>Header: X-API-KEY<br/>Body: [{itemCode, quantity}, ...]

    Note over FastAPI: Pydantic v2 スキーマ検証<br/>・quantity > 0 (field_validator)<br/>・item_code: str 必須
    FastAPI->>Dep: 依存性注入 (DI) 解決

    Dep->>TerminalAuth: get_terminal_info_with_cache(X-API-KEY)
    TerminalAuth-->>Dep: TerminalInfoDocument
    Dep-->>FastAPI: CartService (cart_id セット済み)

    FastAPI->>Router: bulk_reduce_item_quantity(reduce_items, cart_service)

    Note over Router: validate_no_duplicates(reduce_items)<br/>重複 item_code チェック

    Router->>Service: bulk_reduce_line_item_quantity_in_cart_async<br/>([item.model_dump() for item in reduce_items])

    Service->>Redis: cart_repo.get_cached_cart_async(cart_id)<br/>__get_cached_cart_async()
    Redis-->>Service: CartDocument<br/>(status, line_items, masters)

    Note over Service: state_manager.set_state(cart.status)<br/>マスタキャッシュ更新

    Service->>State: check_event_sequence(self)<br/>event = "bulk_reduce_line_item_quantity_in_cart_async"<br/>(inspect.currentframe()で自動検出)
    State-->>Service: OK (EnteringItem 状態で許可)

    Note over Service: active_items dict 構築<br/>{item_code: LineItem} for 非キャンセル行

    Note over Service: ── 全件バリデーション (Atomic Pre-check) ──<br/>① item_code が active_items に存在するか<br/>② reduce_qty ≤ current_qty

    Note over Service: ── 全件更新 (in-memory) ──<br/>line_item.quantity -= reduce_qty

    Service->>Subtotal: __subtotal_async(cart_doc)<br/>calc_subtotal_async(cart_doc, tax_master_repo)
    Note over Subtotal: 行金額・割引・税額・<br/>合計・残高を再計算
    Subtotal-->>Service: CartDocument (totals更新済み)

    Service->>Redis: cart_repo.cache_cart_async(cart_doc)<br/>__cache_cart_async(cart_status=NoUpdate)
    Redis-->>Service: 保存完了

    Service-->>Router: CartDocument

    Router->>Transformer: SchemasTransformerV1().transform_cart(cart_doc)
    Transformer-->>Router: Cart (APIスキーマ)

    Router-->>Client: 200 OK<br/>ApiResponse[Cart]<br/>{success: true, data: {lineItems, totalAmount, ...}}
```

---

## 2. エラー系フロー

### 2-1. リクエストバリデーションエラー (422)

```mermaid
sequenceDiagram
    autonumber
    participant Client as クライアント
    participant FastAPI as FastAPI<br/>(Pydantic検証)
    participant Handler as RouteHandler

    alt quantity = 0 (field_validatorで拒否)
        Client->>FastAPI: PATCH .../bulkQuantityReduce<br/>[{itemCode: "A", quantity: 0}]
        FastAPI-->>Client: 422 Unprocessable Entity<br/>"quantity must be greater than 0"
    end

    alt 重複 item_code
        Client->>FastAPI: PATCH .../bulkQuantityReduce<br/>[{itemCode: "A", quantity:1}, {itemCode: "A", quantity:1}]
        FastAPI->>Handler: 検証通過 (Pydanticは重複を検知しない)
        Handler->>Handler: validate_no_duplicates()<br/>ValueError 発生
        Handler-->>Client: 422 Unprocessable Entity<br/>"Duplicate item_code found in request list"
    end

    alt 空リスト []
        Client->>FastAPI: PATCH .../bulkQuantityReduce<br/>[]
        FastAPI-->>Client: 422 Unprocessable Entity
    end
```

### 2-2. カート未検出エラー (404)

```mermaid
sequenceDiagram
    autonumber
    participant Client as クライアント
    participant Router as RouteHandler
    participant Service as CartService
    participant Redis as Redis<br/>(Dapr State Store)
    participant EH as ExceptionHandler

    Client->>Router: PATCH .../bulkQuantityReduce
    Router->>Service: bulk_reduce_line_item_quantity_in_cart_async(...)
    Service->>Redis: get_cached_cart_async(cart_id)
    Redis-->>Service: キャッシュなし / エラー

    Service->>EH: CartNotFoundException 発生<br/>(Slackアラート送信)
    EH-->>Client: 404 Not Found
```

### 2-3. ステート不正エラー (400) — Paying状態など

```mermaid
sequenceDiagram
    autonumber
    participant Client as クライアント
    participant Router as RouteHandler
    participant Service as CartService
    participant Redis as Redis
    participant State as CartStateManager<br/>/ PayingState
    participant EH as ExceptionHandler

    Client->>Router: PATCH .../bulkQuantityReduce<br/>(カートが Paying 状態)
    Router->>Service: bulk_reduce_line_item_quantity_in_cart_async(...)
    Service->>Redis: get_cached_cart_async(cart_id)
    Redis-->>Service: CartDocument (status = "paying")

    Note over Service: state_manager.set_state("paying")<br/>→ PayingState にセット

    Service->>State: check_event_sequence(self)<br/>event = "bulk_reduce_line_item_quantity_in_cart_async"
    Note over State: allowed_events に含まれない
    State->>EH: EventBadSequenceException 発生<br/>"Invalid event: ... for state: PayingState"
    EH-->>Client: 400 Bad Request
```

### 2-4. 商品未登録エラー (404)

```mermaid
sequenceDiagram
    autonumber
    participant Client as クライアント
    participant Router as RouteHandler
    participant Service as CartService
    participant Redis as Redis
    participant EH as ExceptionHandler

    Client->>Router: PATCH .../bulkQuantityReduce<br/>[{itemCode: "EXIST", qty:1}, {itemCode: "NO_EXIST", qty:1}]
    Router->>Service: bulk_reduce_line_item_quantity_in_cart_async(...)
    Service->>Redis: get_cached_cart_async(cart_id)
    Redis-->>Service: CartDocument

    Note over Service: active_items = {"EXIST": LineItem}

    Note over Service: バリデーションループ<br/>"EXIST" → OK<br/>"NO_EXIST" → active_items に不在

    Service->>EH: ItemNotFoundException 発生<br/>(エラーコード: 402001)
    EH-->>Client: 404 Not Found<br/>{success: false, userError: {code: "402001"}}

    Note over Service: ⚠️ 一切の変更なし<br/>(Atomic: 部分更新しない)
```

### 2-5. 削減数量超過エラー (400)

```mermaid
sequenceDiagram
    autonumber
    participant Client as クライアント
    participant Router as RouteHandler
    participant Service as CartService
    participant Redis as Redis
    participant EH as ExceptionHandler

    Client->>Router: PATCH .../bulkQuantityReduce<br/>[{itemCode: "A", qty:2}, {itemCode: "B", qty:99}]<br/>(カート内: A=3, B=1)
    Router->>Service: bulk_reduce_line_item_quantity_in_cart_async(...)
    Service->>Redis: get_cached_cart_async(cart_id)
    Redis-->>Service: CartDocument

    Note over Service: バリデーションループ<br/>"A": 2 ≤ 3 → OK<br/>"B": 99 > 1 → エラー

    Service->>EH: ItemQuantityReductionExceedsException 発生<br/>(エラーコード: 402006)
    EH-->>Client: 400 Bad Request<br/>{success: false, userError: {code: "402006"}}

    Note over Service: ⚠️ 一切の変更なし<br/>(Atomic: A も更新されない)
```

---

## 3. コンポーネント関係図

```mermaid
graph TB
    subgraph API Layer
        RT[PATCH /carts/{cart_id}/lineItems/bulkQuantityReduce<br/>bulk_reduce_item_quantity]
        SCH[BulkQuantityReductionItem<br/>Pydantic v2 Schema]
        BVAL[BaseBulkQuantityReductionRequest<br/>validate_no_duplicates]
    end

    subgraph Service Layer
        SVC[CartService<br/>bulk_reduce_line_item_quantity_in_cart_async]
        SM[CartStateManager<br/>check_event_sequence]
        EIS[EnteringItemState<br/>allowed_events]
        SUB[calc_subtotal_logic<br/>calc_subtotal_async]
    end

    subgraph Infrastructure
        REPO[CartRepository<br/>get_cached_cart_async<br/>cache_cart_async]
        REDIS[(Redis<br/>Dapr State Store)]
    end

    subgraph Exceptions
        INF[ItemNotFoundException<br/>402001 / HTTP 404]
        EXC[ItemQuantityReductionExceedsException<br/>402006 / HTTP 400]
        EVT[EventBadSequenceException<br/>HTTP 400]
    end

    RT -->|list[BulkQuantityReductionItem]| SCH
    RT -->|validate_no_duplicates| BVAL
    RT -->|list[dict]| SVC

    SVC -->|check_event_sequence| SM
    SM -->|delegates| EIS
    SVC -->|__subtotal_async| SUB
    SVC -->|__get_cached_cart_async| REPO
    SVC -->|__cache_cart_async| REPO
    REPO <-->|Dapr State API| REDIS

    SVC -.->|item not found| INF
    SVC -.->|qty exceeds| EXC
    EIS -.->|bad sequence| EVT
```

---

## 4. Atomicity (アトミック性) の保証

```
PATCH request received
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  Phase 1: 読み取り                                      │
│  Redis から CartDocument を 1回だけ取得                   │
└───────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  Phase 2: 全件バリデーション (変更なし)                     │
│  for each item in reduce_items:                        │
│    ① item_code が存在するか？  → No: 404 で即時中断        │
│    ② reduce_qty ≤ current_qty？→ No: 400 で即時中断        │
└───────────────────────────────────────────────────────┘
        │  全件 OK の場合のみ
        ▼
┌───────────────────────────────────────────────────────┐
│  Phase 3: 全件更新 (in-memory)                          │
│  for each item in reduce_items:                        │
│    line_item.quantity -= reduce_qty                    │
└───────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  Phase 4: 小計再計算                                     │
│  calc_subtotal_async() 1回呼び出し                       │
└───────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  Phase 5: 書き込み                                      │
│  Redis へ CartDocument を 1回だけ保存                     │
└───────────────────────────────────────────────────────┘
        │
        ▼
   200 OK レスポンス

※ Phase 2 でエラーが発生した場合、Phase 3〜5 は実行されず
   カートは一切変更されない（部分更新なし）
```
