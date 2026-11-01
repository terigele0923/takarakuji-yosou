"""Add prediction history and model evaluation tables.

Revision ID: 20261101_0002
Revises: 20261101_0001
"""

from alembic import op

revision = "20261101_0002"
down_revision = "20261101_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lottery TEXT NOT NULL,
            target_round INTEGER NOT NULL,
            source_last_round INTEGER NOT NULL,
            source_draw_count INTEGER NOT NULL,
            requested_count INTEGER NOT NULL,
            generated_at TEXT NOT NULL,
            model_version TEXT NOT NULL,
            response_json TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_prediction_runs_lookup "
        "ON prediction_runs (lottery, target_round, generated_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lottery TEXT NOT NULL,
            source_last_round INTEGER NOT NULL,
            source_draw_count INTEGER NOT NULL,
            evaluated_at TEXT NOT NULL,
            model_version TEXT NOT NULL,
            evaluated_draws INTEGER NOT NULL,
            actual_average_score REAL NOT NULL,
            random_average_score REAL NOT NULL,
            score_lift_percent REAL NOT NULL,
            above_random_rate REAL NOT NULL,
            UNIQUE (lottery, source_last_round, model_version)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_model_evaluations_lookup "
        "ON model_evaluations (lottery, evaluated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_model_evaluations_lookup")
    op.execute("DROP TABLE IF EXISTS model_evaluations")
    op.execute("DROP INDEX IF EXISTS ix_prediction_runs_lookup")
    op.execute("DROP TABLE IF EXISTS prediction_runs")
