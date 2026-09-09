"""Create the production batch-processing schema.

Revision ID: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("batches", sa.Column("id", sa.String(36), primary_key=True), sa.Column("referral", sa.String(120), nullable=False), sa.Column("target", sa.Integer(), nullable=False), sa.Column("successful", sa.Integer(), nullable=False, server_default="0"), sa.Column("failed", sa.Integer(), nullable=False, server_default="0"), sa.Column("status", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_table("jobs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("batch_id", sa.String(36), sa.ForeignKey("batches.id"), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("worker_id", sa.String(120)), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.create_table("authorized_test_identities", sa.Column("id", sa.String(36), primary_key=True), sa.Column("identifier", sa.String(255), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("used_at", sa.DateTime(timezone=True)), sa.Column("batch_id", sa.String(36), sa.ForeignKey("batches.id")), sa.UniqueConstraint("identifier", name="uq_authorized_test_identity_identifier"))
    op.create_table("attempts", sa.Column("id", sa.String(36), primary_key=True), sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("error", sa.Text()), sa.Column("attempt_number", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_table("events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("batch_id", sa.String(36), sa.ForeignKey("batches.id"), nullable=False), sa.Column("event_type", sa.String(80), nullable=False), sa.Column("data", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index("ix_jobs_batch_status", "jobs", ["batch_id", "status"])
    op.create_index("ix_jobs_worker_id", "jobs", ["worker_id"])
    op.create_index("ix_attempts_job_id", "attempts", ["job_id"])


def downgrade() -> None:
    for table in ("events", "attempts", "authorized_test_identities", "jobs", "batches"):
        op.drop_table(table)
