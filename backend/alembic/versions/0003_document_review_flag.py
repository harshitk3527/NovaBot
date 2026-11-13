"""add document review flag"""

from alembic import op
import sqlalchemy as sa

revision = "0003_document_review_flag"
down_revision = "0002_document_processing_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("documents", "needs_review")
