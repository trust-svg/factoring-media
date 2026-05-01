"""add_quality_columns

Revision ID: 0002_add_quality
Revises: 7316290cb6fe
Create Date: 2026-05-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_quality"
down_revision: Union[str, Sequence[str], None] = "7316290cb6fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "quality", sa.String(length=16), nullable=False, server_default="low"
        ),
    )
    op.execute("UPDATE jobs SET quality='low' WHERE quality IS NULL")

    op.add_column(
        "templates",
        sa.Column(
            "default_quality",
            sa.String(length=16),
            nullable=False,
            server_default="low",
        ),
    )
    op.execute(
        "UPDATE templates SET default_quality='low' WHERE default_quality IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("templates") as batch_op:
        batch_op.drop_column("default_quality")
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("quality")
