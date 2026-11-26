"""Create the locked first-run state row."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    settings = sa.table("settings", sa.column("key", sa.String), sa.column("value", sa.JSON))
    op.bulk_insert(settings, [{"key": "bootstrap", "value": {"initialized": False}}])


def downgrade():
    op.execute("DELETE FROM settings WHERE key = 'bootstrap'")
