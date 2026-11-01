"""Store learned bias model weight profiles.

Revision ID: 20261101_0004
Revises: 20261101_0003
"""

from alembic import op

revision = "20261101_0004"
down_revision = "20261101_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bias_model_profiles (
            lottery TEXT PRIMARY KEY,
            model_version TEXT NOT NULL,
            long_weight REAL NOT NULL,
            recent_weight REAL NOT NULL,
            pair_weight REAL NOT NULL,
            learned_at TEXT NOT NULL,
            source_report_hash TEXT NOT NULL,
            training_rounds INTEGER NOT NULL,
            training_exact_hits INTEGER NOT NULL,
            training_total_matches INTEGER NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bias_model_profiles")
