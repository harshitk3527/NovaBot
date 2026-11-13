from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import require_role
from app.db.models import AuditLog, Document, DocumentStatus, User, UserRole
from app.db.session import get_db
from app.schemas.documents import DocumentListResponse, DocumentResponse, DocumentUpdateRequest
from app.services import ingestion
from app.services.documents import active_documents_filter
from app.services.redis_version import get_kb_version, increment_kb_version

router = APIRouter(prefix="/admin/documents", tags=["admin-documents"])
admin_dependency = Depends(require_role(UserRole.ADMIN))


async def _document_for_admin(
    document_id: UUID, user: User, db: AsyncSession
) -> Document:
    document = await db.scalar(
        select(Document)
        .join(User, Document.uploaded_by == User.id)
        .where(Document.id == document_id, User.tenant_id == user.tenant_id)
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("", response_model=DocumentResponse, status_code=202)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    expires_at: datetime | None = Form(default=None),
    user: User = admin_dependency,
    db: AsyncSession = Depends(get_db),
) -> Document:
    settings = get_settings()
    filename = file.filename or ""
    content = await file.read(settings.max_upload_size_bytes + 1)
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="File is too large")
    try:
        extension = ingestion.validate_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    digest = ingestion.content_hash(content)
    duplicate = await db.scalar(
        select(Document)
        .join(User, Document.uploaded_by == User.id)
        .where(
            User.tenant_id == user.tenant_id,
            Document.content_hash == digest,
            Document.status == DocumentStatus.ACTIVE,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="An identical active document already exists")

    document_title = (title or Path(filename).stem).strip()
    if not document_title:
        raise HTTPException(status_code=400, detail="A document title is required")
    previous_versions = (
        await db.scalars(
            select(Document)
            .join(User, Document.uploaded_by == User.id)
            .where(Document.title == document_title, User.tenant_id == user.tenant_id)
            .order_by(Document.created_at.desc())
        )
    ).all()
    version_number = 1
    if previous_versions:
        try:
            version_number = max(int(item.version) for item in previous_versions) + 1
        except ValueError:
            version_number = len(previous_versions) + 1

    document = Document(
        title=document_title,
        version=str(version_number),
        status=DocumentStatus.PROCESSING,
        content_hash=digest,
        valid_from=datetime.now(timezone.utc),
        expires_at=expires_at,
        uploaded_by=user.id,
    )
    db.add(document)
    db.add(
        AuditLog(
            user_id=user.id,
            ip=request.client.host if request.client else None,
            action="document.upload",
            details={
                "filename": filename,
                "extension": extension,
                "document_title": document_title,
            },
        )
    )
    await db.commit()
    await db.refresh(document)
    await increment_kb_version(user.tenant_id)
    background_tasks.add_task(
        ingestion.process_document,
        document.id,
        user.tenant_id,
        filename,
        content,
    )
    return document


@router.put("/{document_id}", response_model=DocumentResponse, status_code=202)
async def replace_document(
    request: Request,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    expires_at: datetime | None = Form(default=None),
    user: User = admin_dependency,
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Upload a new version while retaining the existing document history."""
    previous = await _document_for_admin(document_id, user, db)
    if previous.status == DocumentStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="This document is already being updated")

    settings = get_settings()
    filename = file.filename or ""
    content = await file.read(settings.max_upload_size_bytes + 1)
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="File is too large")
    try:
        extension = ingestion.validate_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    digest = ingestion.content_hash(content)
    duplicate = await db.scalar(
        select(Document)
        .join(User, Document.uploaded_by == User.id)
        .where(
            User.tenant_id == user.tenant_id,
            Document.content_hash == digest,
            Document.status == DocumentStatus.ACTIVE,
            Document.id != previous.id,
        )
    )
    if duplicate is not None or digest == previous.content_hash:
        raise HTTPException(status_code=409, detail="An identical active document already exists")

    versions = (
        await db.scalars(
            select(Document)
            .join(User, Document.uploaded_by == User.id)
            .where(Document.title == previous.title, User.tenant_id == user.tenant_id)
        )
    ).all()
    try:
        version_number = max(int(item.version) for item in versions) + 1
    except ValueError:
        version_number = len(versions) + 1

    document = Document(
        title=previous.title,
        version=str(version_number),
        status=DocumentStatus.PROCESSING,
        content_hash=digest,
        valid_from=datetime.now(timezone.utc),
        expires_at=previous.expires_at if expires_at is None else expires_at,
        uploaded_by=user.id,
    )
    db.add(document)
    db.add(
        AuditLog(
            user_id=user.id,
            ip=request.client.host if request.client else None,
            action="document.replace",
            details={
                "filename": filename,
                "extension": extension,
                "document_id": str(previous.id),
                "replacement_version": str(version_number),
            },
        )
    )
    await db.commit()
    await db.refresh(document)
    await increment_kb_version(user.tenant_id)
    background_tasks.add_task(
        ingestion.process_document,
        document.id,
        user.tenant_id,
        filename,
        content,
    )
    return document


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    user: User = admin_dependency,
    db: AsyncSession = Depends(get_db),
    status: DocumentStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DocumentListResponse:
    base = select(Document).join(User, Document.uploaded_by == User.id).where(User.tenant_id == user.tenant_id)
    count_query = select(func.count()).select_from(Document).join(User, Document.uploaded_by == User.id).where(
        User.tenant_id == user.tenant_id
    )
    if status is not None:
        base = base.where(Document.status == status)
        count_query = count_query.where(Document.status == status)
    total = await db.scalar(count_query) or 0
    documents = (
        await db.scalars(
            base.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return DocumentListResponse(items=list(documents), page=page, page_size=page_size, total=total)


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    request: Request,
    document_id: UUID,
    payload: DocumentUpdateRequest,
    user: User = admin_dependency,
    db: AsyncSession = Depends(get_db),
) -> Document:
    document = await _document_for_admin(document_id, user, db)
    changes: dict[str, object] = {}
    if payload.status == "archive":
        document.status = DocumentStatus.ARCHIVED
        changes["status"] = "archived"
    elif payload.status == "approve":
        document.needs_review = False
        changes["needs_review"] = False
    if "expires_at" in payload.model_fields_set:
        document.expires_at = payload.expires_at
        changes["expires_at"] = payload.expires_at.isoformat() if payload.expires_at else None
    if not changes:
        raise HTTPException(status_code=400, detail="No document changes supplied")
    db.add(
        AuditLog(
            user_id=user.id,
            ip=request.client.host if request.client else None,
            action=(
                "document.archive"
                if payload.status == "archive"
                else "document.approve"
                if payload.status == "approve"
                else "document.update"
            ),
            details={"document_id": str(document.id), "changes": changes},
        )
    )
    await db.commit()
    await db.refresh(document)
    await increment_kb_version(user.tenant_id)
    return document


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    request: Request,
    document_id: UUID,
    user: User = admin_dependency,
    db: AsyncSession = Depends(get_db),
) -> None:
    document = await _document_for_admin(document_id, user, db)
    await db.execute(
        update(Document).where(Document.superseded_by == document.id).values(superseded_by=None)
    )
    db.add(
        AuditLog(
            user_id=user.id,
            ip=request.client.host if request.client else None,
            action="document.delete",
            details={"document_id": str(document.id)},
        )
    )
    await db.delete(document)
    await db.commit()
    await increment_kb_version(user.tenant_id)


@router.get("/version/current")
async def current_kb_version(user: User = admin_dependency) -> dict[str, int]:
    return {"kb_version": await get_kb_version(user.tenant_id)}


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    user: User = admin_dependency,
    db: AsyncSession = Depends(get_db),
) -> Document:
    return await _document_for_admin(document_id, user, db)
