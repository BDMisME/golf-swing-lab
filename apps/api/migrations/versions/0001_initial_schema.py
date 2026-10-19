"""Initial Golf Swing Lab schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-10-19 14:35:00

"""
from collections.abc import Sequence

from alembic import op

import apps.api.models  # noqa: F401
from apps.api.db import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
