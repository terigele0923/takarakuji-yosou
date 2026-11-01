"""Store half-life profiles and advanced training runs.

Revision ID: 20261101_0005
Revises: 20261101_0004
"""

from alembic import op

revision = "20261101_0005"
down_revision = "20261101_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {
        row[1]
        for row in connection.exec_driver_sql(
            "PRAGMA table_info('bias_model_profiles')"
        ).fetchall()
    }
    if "recent_half_life" not in columns:
        op.execute(
            "ALTER TABLE bias_model_profiles "
            "ADD COLUMN recent_half_life INTEGER NOT NULL DEFAULT 40"
        )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_training_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lottery TEXT NOT NULL,
            created_at TEXT NOT NULL,
            folds INTEGER NOT NULL,
            validation_months INTEGER NOT NULL,
            test_months INTEGER NOT NULL,
            candidate_model_version TEXT NOT NULL,
            long_weight REAL NOT NULL,
            recent_weight REAL NOT NULL,
            pair_weight REAL NOT NULL,
            recent_half_life INTEGER NOT NULL,
            evaluated_draws INTEGER NOT NULL,
            mean_actual_rank REAL NOT NULL,
            mean_rank_percentile REAL NOT NULL,
            average_best_matches REAL NOT NULL,
            random_average_best_matches REAL NOT NULL,
            match_lift REAL NOT NULL,
            confidence_low REAL NOT NULL,
            confidence_high REAL NOT NULL,
            exact_hits INTEGER NOT NULL,
            promoted INTEGER NOT NULL,
            report_json TEXT NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_training_runs")
