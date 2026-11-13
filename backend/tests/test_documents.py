from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Document, DocumentStatus, User, UserRole
from app.db import session as db_session
from app.services.documents import active_documents_filter
from app.services import ingestion


async def make_admin(client) -> tuple[str, str]:
    email = f"{uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "correct horse battery"})
    async with db_session.AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        user.role = UserRole.ADMIN
        await db.commit()
    login = await client.post(
        "/auth/login", json={"email": email, "password": "correct horse battery"}
    )
    return email, login.json()["access_token"]


async def no_op_embeddings(texts):
    return [[0.0] * 1536 for _ in texts]


@pytest.mark.asyncio
async def test_duplicate_upload_rejected(client, monkeypatch):
    _, token = await make_admin(client)
    monkeypatch.setattr(ingestion, "embed_chunks", no_op_embeddings)
    headers = {"Authorization": f"Bearer {token}"}
    upload = {"file": ("guide.txt", b"same content", "text/plain")}
    first = await client.post("/admin/documents", headers=headers, files=upload)
    assert first.status_code == 202
    duplicate = await client.post("/admin/documents", headers=headers, files=upload)
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_new_version_supersedes_old(client, monkeypatch):
    _, token = await make_admin(client)
    monkeypatch.setattr(ingestion, "embed_chunks", no_op_embeddings)
    headers = {"Authorization": f"Bearer {token}"}
    first = await client.post(
        "/admin/documents",
        headers=headers,
        data={"title": "Support Guide"},
        files={"file": ("guide.txt", b"version one", "text/plain")},
    )
    second = await client.post(
        "/admin/documents",
        headers=headers,
        data={"title": "Support Guide"},
        files={"file": ("guide.txt", b"version two", "text/plain")},
    )
    assert first.status_code == second.status_code == 202
    async with db_session.AsyncSessionLocal() as db:
        documents = (
            await db.scalars(select(Document).where(Document.title == "Support Guide"))
        ).all()
    assert sorted(document.version for document in documents) == ["1", "2"]
    old = next(document for document in documents if document.version == "1")
    new = next(document for document in documents if document.version == "2")
    assert old.status == DocumentStatus.SUPERSEDED
    assert old.superseded_by == new.id


@pytest.mark.asyncio
async def test_update_document_creates_next_version(client, monkeypatch):
    _, token = await make_admin(client)
    monkeypatch.setattr(ingestion, "embed_chunks", no_op_embeddings)
    headers = {"Authorization": f"Bearer {token}"}
    first = await client.post(
        "/admin/documents",
        headers=headers,
        data={"title": "Release Notes"},
        files={"file": ("notes.txt", b"first release", "text/plain")},
    )
    replacement = await client.put(
        f"/admin/documents/{first.json()['id']}",
        headers=headers,
        files={"file": ("notes.txt", b"second release", "text/plain")},
    )

    assert replacement.status_code == 202
    assert replacement.json()["title"] == "Release Notes"
    assert replacement.json()["version"] == "2"


@pytest.mark.asyncio
async def test_expired_document_is_excluded_without_job(client):
    _, token = await make_admin(client)
    async with db_session.AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.role == UserRole.ADMIN))
        document = Document(
            title="Expired",
            version="1",
            status=DocumentStatus.ACTIVE,
            content_hash=uuid4().hex,
            valid_from=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            uploaded_by=user.id,
        )
        db.add(document)
        await db.commit()
        result = await db.scalar(
            select(Document)
            .join(User, Document.uploaded_by == User.id)
            .where(active_documents_filter(user.tenant_id))
        )
    assert result is None


@pytest.mark.asyncio
async def test_documents_needing_review_are_excluded(client):
    _, token = await make_admin(client)
    async with db_session.AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.role == UserRole.ADMIN))
        document = Document(
            title="Poisoned",
            version="1",
            status=DocumentStatus.ACTIVE,
            needs_review=True,
            content_hash=uuid4().hex,
            valid_from=datetime.now(timezone.utc),
            uploaded_by=user.id,
        )
        db.add(document)
        await db.commit()
        result = await db.scalar(
            select(Document)
            .join(User, Document.uploaded_by == User.id)
            .where(active_documents_filter(user.tenant_id))
        )
    assert result is None


@pytest.mark.asyncio
async def test_non_admin_gets_403(client):
    register = await client.post(
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "correct horse battery"},
    )
    login = await client.post(
        "/auth/login",
        json={
            "email": register.json()["email"],
            "password": "correct horse battery",
        },
    )
    response = await client.get(
        "/admin/documents",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_invalid_type_and_oversized_file_rejected(client, monkeypatch):
    _, token = await make_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    invalid = await client.post(
        "/admin/documents",
        headers=headers,
        files={"file": ("guide.exe", b"not allowed", "application/octet-stream")},
    )
    assert invalid.status_code == 400

    settings = get_settings()
    original_limit = settings.max_upload_size_bytes
    settings.max_upload_size_bytes = 3
    try:
        oversized = await client.post(
            "/admin/documents",
            headers=headers,
            files={"file": ("guide.txt", b"too large", "text/plain")},
        )
    finally:
        settings.max_upload_size_bytes = original_limit
    assert oversized.status_code == 413
