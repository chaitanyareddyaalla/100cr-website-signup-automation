"""Add skipped, attempted, and retries columns to batches table.

Revision ID: 0002_add_batch_metrics
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_batch_metrics"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("batches", sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("batches", sa.Column("attempted", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("batches", sa.Column("retries", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("batches", "retries")
    op.drop_column("batches", "attempted")
    op.drop_column("batches", "skipped")
