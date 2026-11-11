"""Add an optional job closing date."""

import sqlalchemy as sa
from alembic import op

revision = "0003_job_closing_date"
down_revision = "0002_manual_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("closing_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "closing_date")
