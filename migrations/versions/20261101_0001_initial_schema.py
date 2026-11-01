"""Create the initial lottery, prize, and purchase schema.

Revision ID: 20261101_0001
Revises: None
"""

from alembic import op

revision = "20261101_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS makes this baseline safe for databases created before Alembic was introduced.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS draws (
            lottery TEXT NOT NULL,
            round INTEGER NOT NULL,
            draw_date TEXT NOT NULL,
            numbers TEXT NOT NULL,
            bonus TEXT NOT NULL,
            PRIMARY KEY (lottery, round)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prizes (
            lottery TEXT NOT NULL,
            round INTEGER NOT NULL,
            tier TEXT NOT NULL,
            amount INTEGER NOT NULL,
            PRIMARY KEY (lottery, round, tier)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lottery TEXT NOT NULL,
            round INTEGER NOT NULL,
            numbers TEXT NOT NULL,
            play_type TEXT NOT NULL,
            price INTEGER NOT NULL,
            purchased_at TEXT NOT NULL,
            tier TEXT,
            prize INTEGER
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_purchases_pending "
        "ON purchases (lottery, round) WHERE prize IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_purchases_pending")
    op.execute("DROP TABLE IF EXISTS purchases")
    op.execute("DROP TABLE IF EXISTS prizes")
    op.execute("DROP TABLE IF EXISTS draws")
