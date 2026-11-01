-- 過去の抽選結果を保存する表（宝くじの種類と回で1行）
CREATE TABLE IF NOT EXISTS draws (
    lottery   TEXT    NOT NULL,  -- 種類（numbers3, numbers4, miniloto, loto6, loto7）
    round     INTEGER NOT NULL,  -- 回
    draw_date TEXT    NOT NULL,  -- 抽選日（YYYY-MM-DD）
    numbers   TEXT    NOT NULL,  -- 本数字（カンマ区切り。例：1,5,12,19,30,41。ナンバーズは桁の順）
    bonus     TEXT    NOT NULL,  -- ボーナス数字（カンマ区切り。例：22。ナンバーズは空）
    PRIMARY KEY (lottery, round)
);

-- 等級ごとの賞金（回ごと）
CREATE TABLE IF NOT EXISTS prizes (
    lottery TEXT    NOT NULL,  -- 種類
    round   INTEGER NOT NULL,  -- 回
    tier    TEXT    NOT NULL,  -- 等級（1等、ストレート、セット・ボックス など）
    amount  INTEGER NOT NULL,  -- 1口あたりの賞金（円）
    PRIMARY KEY (lottery, round, tier)
);

-- 購入した記録
CREATE TABLE IF NOT EXISTS purchases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery      TEXT    NOT NULL,  -- 種類
    round        INTEGER NOT NULL,  -- 買った回
    numbers      TEXT    NOT NULL,  -- 番号（カンマ区切り。ミニは下2桁）
    play_type    TEXT    NOT NULL,  -- 申込タイプ（ロト系は normal、ナンバーズは straight / box / set / mini）
    price        INTEGER NOT NULL,  -- 金額（円）
    purchased_at TEXT    NOT NULL,  -- 記録した日時
    tier         TEXT,              -- 結果の等級（外れ・未確認は NULL）
    prize        INTEGER            -- 当たった金額（未確認は NULL）
);

-- 未確認購入と抽せん結果の照合を高速化する索引
CREATE INDEX IF NOT EXISTS ix_purchases_pending
ON purchases (lottery, round)
WHERE prize IS NULL;

-- 画面で生成した予想結果の履歴
CREATE TABLE IF NOT EXISTS prediction_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery           TEXT    NOT NULL,
    target_round      INTEGER NOT NULL,
    source_last_round INTEGER NOT NULL,
    source_draw_count INTEGER NOT NULL,
    requested_count   INTEGER NOT NULL,
    generated_at      TEXT    NOT NULL,
    model_version     TEXT    NOT NULL,
    response_json     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_prediction_runs_lookup
ON prediction_runs (lottery, target_round, generated_at DESC);

-- 抽選データの最終回ごとに保存する偏りモデルの評価結果
CREATE TABLE IF NOT EXISTS model_evaluations (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery                TEXT    NOT NULL,
    source_last_round      INTEGER NOT NULL,
    source_draw_count      INTEGER NOT NULL,
    evaluated_at           TEXT    NOT NULL,
    model_version          TEXT    NOT NULL,
    evaluated_draws        INTEGER NOT NULL,
    actual_average_score   REAL    NOT NULL,
    random_average_score   REAL    NOT NULL,
    score_lift_percent     REAL    NOT NULL,
    above_random_rate      REAL    NOT NULL,
    UNIQUE (lottery, source_last_round, model_version)
);

CREATE INDEX IF NOT EXISTS ix_model_evaluations_lookup
ON model_evaluations (lottery, evaluated_at DESC);

-- 評価レポートから収支へ取り込んだ購入の二重登録を防ぐ
CREATE TABLE IF NOT EXISTS purchase_imports (
    source_ref  TEXT    PRIMARY KEY,
    purchase_id INTEGER NOT NULL UNIQUE,
    imported_at TEXT    NOT NULL,
    FOREIGN KEY (purchase_id) REFERENCES purchases (id)
);

-- ウォークフォワード結果から学習した種類別の偏りモデル重み
CREATE TABLE IF NOT EXISTS bias_model_profiles (
    lottery                    TEXT PRIMARY KEY,
    model_version              TEXT NOT NULL,
    long_weight                REAL NOT NULL,
    recent_weight              REAL NOT NULL,
    pair_weight                REAL NOT NULL,
    recent_half_life           INTEGER NOT NULL DEFAULT 40,
    learned_at                 TEXT NOT NULL,
    source_report_hash         TEXT NOT NULL,
    training_rounds            INTEGER NOT NULL,
    training_exact_hits        INTEGER NOT NULL,
    training_total_matches     INTEGER NOT NULL
);

-- 複数の未使用期間で評価した高度学習の履歴
CREATE TABLE IF NOT EXISTS model_training_runs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    lottery                     TEXT NOT NULL,
    created_at                  TEXT NOT NULL,
    folds                       INTEGER NOT NULL,
    validation_months           INTEGER NOT NULL,
    test_months                 INTEGER NOT NULL,
    candidate_model_version     TEXT NOT NULL,
    long_weight                 REAL NOT NULL,
    recent_weight               REAL NOT NULL,
    pair_weight                 REAL NOT NULL,
    recent_half_life            INTEGER NOT NULL,
    evaluated_draws             INTEGER NOT NULL,
    mean_actual_rank            REAL NOT NULL,
    mean_rank_percentile        REAL NOT NULL,
    average_best_matches        REAL NOT NULL,
    random_average_best_matches REAL NOT NULL,
    match_lift                  REAL NOT NULL,
    confidence_low              REAL NOT NULL,
    confidence_high             REAL NOT NULL,
    exact_hits                  INTEGER NOT NULL,
    promoted                    INTEGER NOT NULL,
    report_json                 TEXT NOT NULL
);
