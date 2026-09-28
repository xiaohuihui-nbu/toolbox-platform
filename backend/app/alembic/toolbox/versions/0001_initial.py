"""Frozen Toolbox v0.1 MySQL schema. Future changes must add a new revision."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    schema = (Path(__file__).parent / "0001_schema.sql").read_text(encoding="utf-8")
    for statement in schema.split(";"):
        if statement.strip():
            op.execute(sa.text(statement))


def downgrade():
    for table in ["tb_assets", "tb_outbox", "tb_jobs", "tb_tool_settings", "tb_users"]:
        op.drop_table(table)
