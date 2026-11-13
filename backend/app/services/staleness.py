from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import AuditLog, Document, DocumentStatus, User
from app.db.session import AsyncSessionLocal
from app.services.redis_version import increment_kb_version


async def expire_stale_documents() -> int:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            documents = (
                await db.scalars(
                    select(Document)
                    .join(User, Document.uploaded_by == User.id)
                    .where(
                        Document.status == DocumentStatus.ACTIVE,
                        Document.expires_at.is_not(None),
                        Document.expires_at <= datetime.now(timezone.utc),
                    )
                    .with_for_update()
                )
            ).all()
            tenant_ids = set()
            for document in documents:
                document.status = DocumentStatus.EXPIRED
                tenant_id = await db.scalar(select(User.tenant_id).where(User.id == document.uploaded_by))
                if tenant_id is not None:
                    tenant_ids.add(tenant_id)
                db.add(
                    AuditLog(
                        user_id=None,
                        action="document.expire",
                        details={"document_id": str(document.id)},
                    )
                )
        for tenant_id in tenant_ids:
            await increment_kb_version(tenant_id)
        return len(documents)
