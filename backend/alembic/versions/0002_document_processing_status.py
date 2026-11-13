"""add document processing statuses"""

from alembic import op

revision = "0002_document_processing_status"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'processing'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'failed'")


def downgrade() -> None:
    raise NotImplementedError("PostgreSQL enum value removal requires a manual migration")
