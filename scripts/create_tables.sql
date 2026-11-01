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
