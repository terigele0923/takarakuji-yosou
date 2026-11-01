"""Track purchases imported from evaluation reports.

Revision ID: 20261101_0003
Revises: 20261101_0002
"""

from alembic import op

revision = "20261101_0003"
down_revision = "20261101_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_imports (
            source_ref TEXT PRIMARY KEY,
            purchase_id INTEGER NOT NULL UNIQUE,
            imported_at TEXT NOT NULL,
            FOREIGN KEY (purchase_id) REFERENCES purchases (id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS purchase_imports")
