from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.security import create_token


@pytest.mark.asyncio
async def test_register(client):
    response = await client.post(
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "customer"


@pytest.mark.asyncio
async def test_login(client):
    email = f"{uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "correct horse battery"})
    response = await client.post(
        "/auth/login", json={"email": email, "password": "correct horse battery"}
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_wrong_password(client):
    email = f"{uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "correct horse battery"})
    response = await client.post("/auth/login", json={"email": email, "password": "wrong password"})
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "request_error", "message": "Invalid email or password"}
    }


@pytest.mark.asyncio
async def test_expired_token(client):
    token, _ = create_token(uuid4(), "access", timedelta(seconds=-1))
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid or expired credentials"


@pytest.mark.asyncio
async def test_customer_cannot_access_admin_route(client):
    email = f"{uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "correct horse battery"})
    login = await client.post(
        "/auth/login", json={"email": email, "password": "correct horse battery"}
    )
    response = await client.get(
        "/auth/admin-test",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403
