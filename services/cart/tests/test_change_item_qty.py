# Copyright 2025 masa@kugel  # # Licensed under the Apache License, Version 2.0 (the "License");  # you may not use this file except in compliance with the License.  # You may obtain a copy of the License at  # #     http://www.apache.org/licenses/LICENSE-2.0  # # Unless required by applicable law or agreed to in writing, software  # distributed under the License is distributed on an "AS IS" BASIS,  # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  # See the License for the specific language governing permissions and  # limitations under the License.
import pytest
import os
from fastapi import status
from httpx import AsyncClient


# ヘルパー関数 - 認証トークンの取得
async def get_authentication_token():
    tenant_id = os.environ.get("TENANT_ID")
    token_url = os.environ.get("TOKEN_URL")
    login_data = {"username": "admin", "password": "admin", "client_id": tenant_id}

    async with AsyncClient() as http_auth_client:
        response = await http_auth_client.post(url=token_url, data=login_data)
        assert response.status_code == status.HTTP_200_OK
        return response.json().get("access_token")


# ヘルパー関数 - ターミナル情報の取得
async def get_terminal_info():
    terminal_id = os.environ.get("TERMINAL_ID")
    api_key = os.environ.get("API_KEY")
    base_url = os.environ.get("BASE_URL_TERMINAL")
    header = {"X-API-KEY": api_key}

    async with AsyncClient(base_url=base_url) as http_terminal_client:
        response = await http_terminal_client.get(f"/terminals/{terminal_id}", headers=header)

    assert response.status_code == status.HTTP_200_OK
    return response.json().get("data")


# ヘルパー関数 - カート作成
async def create_cart(http_client, terminal_id, api_key):
    """カートを作成してcart_idを返す"""
    header = {"X-API-KEY": api_key}
    cart_data = {"transaction_type": 101, "user_id": "99", "user_name": "Test User"}

    response = await http_client.post(
        f"/api/v1/carts?terminal_id={terminal_id}", json=cart_data, headers=header
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json().get("data", {}).get("cartId")


# ヘルパー関数 - 商品追加
async def add_items(http_client, cart_id, terminal_id, api_key, items):
    """カートに商品を追加してレスポンスを返す"""
    header = {"X-API-KEY": api_key}

    response = await http_client.post(
        f"/api/v1/carts/{cart_id}/lineItems?terminal_id={terminal_id}",
        json=items,
        headers=header,
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json().get("data", {})


# ヘルパー関数 - 行Noを指定して数量変更（新API）
async def change_quantity(http_client, cart_id, terminal_id, api_key, line_no, quantity):
    """PATCH /api/v1/carts/{cart_id}/lineItems/quantity で数量を変更する"""
    header = {"X-API-KEY": api_key}
    body = {"line_no": line_no, "quantity": quantity}

    return await http_client.patch(
        f"/api/v1/carts/{cart_id}/lineItems/quantity?terminal_id={terminal_id}",
        json=body,
        headers=header,
    )


# T009: ハッピーパス - 行Noを指定して数量変更が正常に完了すること
@pytest.mark.asyncio
async def test_change_item_quantity_happy_path(http_client: AsyncClient):
    """
    US1: 行Noを指定してカート内商品の数量を変更できる（正常系）
    カート作成 → 商品追加(数量2) → 行No1の数量を5に変更 → 数量が5になっていること
    """
    terminal_info = await get_terminal_info()
    terminal_id = terminal_info["terminalId"]
    api_key = terminal_info.get("apiKey")

    # カート作成
    cart_id = await create_cart(http_client, terminal_id, api_key)

    # 商品追加（数量2）
    await add_items(http_client, cart_id, terminal_id, api_key, [{"itemCode": "49-01", "quantity": 2}])

    # 行No1の数量を5に変更
    response = await change_quantity(http_client, cart_id, terminal_id, api_key, line_no=1, quantity=5)

    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res.get("success") is True
    data = res.get("data", {})
    line_items = data.get("lineItems", [])
    assert len(line_items) >= 1
    assert line_items[0].get("lineNo") == 1
    assert line_items[0].get("quantity") == 5

    # カートをキャンセルしてクリーンアップ
    header = {"X-API-KEY": api_key}
    await http_client.post(f"/api/v1/carts/{cart_id}/cancel?terminal_id={terminal_id}", headers=header)


# T019: 複数商品のカートで指定した行Noの商品だけが更新されること
@pytest.mark.asyncio
async def test_change_quantity_only_specified_line_updated(http_client: AsyncClient):
    """
    US1 Acceptance Scenario 2: 複数商品のカートで行No1の数量を変更しても、行No2は変更されないこと
    カート作成 → 商品A追加(行No1) + 商品B追加(行No2) → 行No1の数量変更 → 行No2は変更されていないこと
    """
    terminal_info = await get_terminal_info()
    terminal_id = terminal_info["terminalId"]
    api_key = terminal_info.get("apiKey")

    # カート作成
    cart_id = await create_cart(http_client, terminal_id, api_key)

    # 2商品追加（行No1: 数量1, 行No2: 数量3）
    cart_data = await add_items(
        http_client,
        cart_id,
        terminal_id,
        api_key,
        [{"itemCode": "49-01", "quantity": 1}, {"itemCode": "49-01", "quantity": 3}],
    )
    line_items_before = cart_data.get("lineItems", [])
    qty_line2_before = line_items_before[1].get("quantity") if len(line_items_before) >= 2 else 3

    # 行No1の数量を7に変更
    response = await change_quantity(http_client, cart_id, terminal_id, api_key, line_no=1, quantity=7)

    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res.get("success") is True
    line_items = res.get("data", {}).get("lineItems", [])
    assert len(line_items) >= 2

    # 行No1が7になっていること
    assert line_items[0].get("lineNo") == 1
    assert line_items[0].get("quantity") == 7

    # 行No2は変更されていないこと
    assert line_items[1].get("lineNo") == 2
    assert line_items[1].get("quantity") == qty_line2_before

    # クリーンアップ
    header = {"X-API-KEY": api_key}
    await http_client.post(f"/api/v1/carts/{cart_id}/cancel?terminal_id={terminal_id}", headers=header)


# T020: 入力不可状態（Idle）ではエラーになること（FR-006: ステートマシン検証）
@pytest.mark.asyncio
async def test_change_quantity_rejected_in_idle_state(http_client: AsyncClient):
    """
    FR-006: カートがentering_item以外の状態（Idle）では数量変更はエラーになること
    カート作成のみ（商品未追加 = Idle状態）→ 数量変更API呼び出し → エラーレスポンスが返ること
    """
    terminal_info = await get_terminal_info()
    terminal_id = terminal_info["terminalId"]
    api_key = terminal_info.get("apiKey")

    # カート作成のみ（Idle状態）
    cart_id = await create_cart(http_client, terminal_id, api_key)

    # Idle状態で数量変更を試みる
    response = await change_quantity(http_client, cart_id, terminal_id, api_key, line_no=1, quantity=3)

    # ステートマシン（EventBadSequenceException）によりHTTP 400が返ること
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    res = response.json()
    assert res.get("success") is False

    # クリーンアップ
    header = {"X-API-KEY": api_key}
    await http_client.post(f"/api/v1/carts/{cart_id}/cancel?terminal_id={terminal_id}", headers=header)


# T012: 存在しない行Noを指定した場合は400エラーになること
@pytest.mark.asyncio
async def test_change_quantity_invalid_line_no(http_client: AsyncClient):
    """
    US2: 存在しない行No（カートの行数を超える値）を指定すると400エラーになること
    エラーコードが402006（LINE_ITEM_NOT_FOUND）であること
    """
    terminal_info = await get_terminal_info()
    terminal_id = terminal_info["terminalId"]
    api_key = terminal_info.get("apiKey")

    # カート作成 + 商品1つ追加（行Noは1のみ）
    cart_id = await create_cart(http_client, terminal_id, api_key)
    await add_items(http_client, cart_id, terminal_id, api_key, [{"itemCode": "49-01", "quantity": 1}])

    # 存在しない行No（99）を指定
    response = await change_quantity(http_client, cart_id, terminal_id, api_key, line_no=99, quantity=3)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    res = response.json()
    assert res.get("success") is False
    # エラーコード 402006 が含まれること
    assert "402006" in str(res)

    # クリーンアップ
    header = {"X-API-KEY": api_key}
    await http_client.post(f"/api/v1/carts/{cart_id}/cancel?terminal_id={terminal_id}", headers=header)


# T013: キャンセル済みの行Noを指定した場合は400エラーになること
@pytest.mark.asyncio
async def test_change_quantity_cancelled_line(http_client: AsyncClient):
    """
    US4: キャンセル済みの行Noを指定すると400エラーになること
    エラーコードが402006（LINE_ITEM_NOT_FOUND）であること
    """
    terminal_info = await get_terminal_info()
    terminal_id = terminal_info["terminalId"]
    api_key = terminal_info.get("apiKey")
    header = {"X-API-KEY": api_key}

    # カート作成 + 2商品追加
    cart_id = await create_cart(http_client, terminal_id, api_key)
    await add_items(
        http_client,
        cart_id,
        terminal_id,
        api_key,
        [{"itemCode": "49-01", "quantity": 1}, {"itemCode": "49-01", "quantity": 2}],
    )

    # 行No1をキャンセル
    response = await http_client.post(
        f"/api/v1/carts/{cart_id}/lineItems/1/cancel?terminal_id={terminal_id}", headers=header
    )
    assert response.status_code == status.HTTP_200_OK

    # キャンセル済みの行No1に数量変更を試みる
    response = await change_quantity(http_client, cart_id, terminal_id, api_key, line_no=1, quantity=5)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    res = response.json()
    assert res.get("success") is False
    # エラーコード 402006 が含まれること
    assert "402006" in str(res)

    # クリーンアップ
    await http_client.post(f"/api/v1/carts/{cart_id}/cancel?terminal_id={terminal_id}", headers=header)


# T014: quantity=100（上限超え）は422エラーになること
@pytest.mark.asyncio
async def test_change_quantity_exceeds_maximum(http_client: AsyncClient):
    """
    US3: quantityが100（上限99超え）の場合は422 Unprocessable Entityエラーになること
    Pydanticバリデーション（le=99）によるリクエスト検証
    """
    terminal_info = await get_terminal_info()
    terminal_id = terminal_info["terminalId"]
    api_key = terminal_info.get("apiKey")

    # カート作成 + 商品追加
    cart_id = await create_cart(http_client, terminal_id, api_key)
    await add_items(http_client, cart_id, terminal_id, api_key, [{"itemCode": "49-01", "quantity": 1}])

    # quantity=100 で変更試行
    response = await change_quantity(http_client, cart_id, terminal_id, api_key, line_no=1, quantity=100)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # クリーンアップ
    header = {"X-API-KEY": api_key}
    await http_client.post(f"/api/v1/carts/{cart_id}/cancel?terminal_id={terminal_id}", headers=header)


# T015: quantity=0（下限未満）は422エラーになること
@pytest.mark.asyncio
async def test_change_quantity_below_minimum(http_client: AsyncClient):
    """
    US3: quantityが0（下限1未満）の場合は422 Unprocessable Entityエラーになること
    Pydanticバリデーション（ge=1）によるリクエスト検証
    """
    terminal_info = await get_terminal_info()
    terminal_id = terminal_info["terminalId"]
    api_key = terminal_info.get("apiKey")

    # カート作成 + 商品追加
    cart_id = await create_cart(http_client, terminal_id, api_key)
    await add_items(http_client, cart_id, terminal_id, api_key, [{"itemCode": "49-01", "quantity": 1}])

    # quantity=0 で変更試行
    response = await change_quantity(http_client, cart_id, terminal_id, api_key, line_no=1, quantity=0)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # クリーンアップ
    header = {"X-API-KEY": api_key}
    await http_client.post(f"/api/v1/carts/{cart_id}/cancel?terminal_id={terminal_id}", headers=header)


# T016: quantity=99（上限境界値）は正常に変更されること
@pytest.mark.asyncio
async def test_change_quantity_boundary_maximum(http_client: AsyncClient):
    """
    US3: quantityが99（上限境界値）の場合は正常に変更できること
    境界値テスト: 99は許容範囲内
    """
    terminal_info = await get_terminal_info()
    terminal_id = terminal_info["terminalId"]
    api_key = terminal_info.get("apiKey")

    # カート作成 + 商品追加
    cart_id = await create_cart(http_client, terminal_id, api_key)
    await add_items(http_client, cart_id, terminal_id, api_key, [{"itemCode": "49-01", "quantity": 1}])

    # quantity=99（上限境界値）で変更
    response = await change_quantity(http_client, cart_id, terminal_id, api_key, line_no=1, quantity=99)

    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res.get("success") is True
    line_items = res.get("data", {}).get("lineItems", [])
    assert len(line_items) >= 1
    assert line_items[0].get("quantity") == 99

    # クリーンアップ
    header = {"X-API-KEY": api_key}
    await http_client.post(f"/api/v1/carts/{cart_id}/cancel?terminal_id={terminal_id}", headers=header)
