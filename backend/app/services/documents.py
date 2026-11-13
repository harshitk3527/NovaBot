from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.db.models import Document, DocumentStatus, User


def active_documents_filter(tenant_id: UUID | None = None):
    conditions = [
        Document.status == DocumentStatus.ACTIVE,
        or_(Document.expires_at.is_(None), Document.expires_at > func.now()),
    ]
    if tenant_id is not None:
        conditions.append(
            Document.uploaded_by.in_(select(User.id).where(User.tenant_id == tenant_id))
        )
    return and_(*conditions)
