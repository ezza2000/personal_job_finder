"""Add CSV previews, editable candidate profile, duplicate review, and optional job URLs."""

import sqlalchemy as sa
from alembic import op

revision = "0002_manual_imports"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.alter_column("original_url", existing_type=sa.Text(), nullable=True)

    op.create_table(
        "candidate_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("education", sa.Text(), nullable=False, server_default=""),
        sa.Column("placement", sa.Text(), nullable=False, server_default=""),
        sa.Column("experience_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "duplicate_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "first_job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "second_job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("similarity", sa.Integer(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("review_state", sa.String(24), nullable=False, server_default="needs_review"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_duplicate_candidates_state", "duplicate_candidates", ["review_state"])
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="preview"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("import_batches")
    op.drop_index("ix_duplicate_candidates_state", table_name="duplicate_candidates")
    op.drop_table("duplicate_candidates")
    op.drop_table("candidate_profile")
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.alter_column("original_url", existing_type=sa.Text(), nullable=False)
