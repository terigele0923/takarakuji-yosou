import datetime

from pydantic import BaseModel, Field

from app.schemas.lottery import LotteryType
from app.schemas.odds import TierOdds

# 一度に予想できる組数の上限
MAX_SETS = 10


class LotteryOption(BaseModel):
    """画面の選択肢に出す宝くじの種類"""

    value: LotteryType
    name: str


class PredictRequest(BaseModel):
    lottery: LotteryType
    count: int = Field(default=1, ge=1, le=MAX_SETS)  # 予想する組数


class PredictedSet(BaseModel):
    """予想した番号1組"""

    numbers: list[int]       # 番号（ロト系は小さい順、ナンバーズは左の桁から）
    reason: str              # 選んだ理由
    odds: list[TierOdds]     # 申込タイプ・等級ごとの当せん確率
    rank: int                # 偏り予測スコア順位
    bias_score: float         # 長期・直近・ペアの偏りを統合した0〜100のスコア
    bias_components: dict[str, float]  # 偏りスコアの内訳
    trend_score: float        # 過去データとの類似度（当せん確率ではない）
    average_distance: float   # 過去の全抽せん結果との平均距離
    closest_round: int        # 距離が最小だった過去の回
    closest_distance: float   # 過去の結果との最小距離
    match_distribution: list[int]  # 0一致〜全一致の回数


class FrequencyMatrix(BaseModel):
    """番号または桁位置ごとの出現回数"""

    title: str
    labels: list[str]
    counts: list[int]
    total_draws: int


class CooccurrenceMatrix(BaseModel):
    """番号ペアまたは桁位置ペアの同時出現回数と条件付き割合"""

    title: str
    row_labels: list[str]
    column_labels: list[str]
    counts: list[list[int]]
    probabilities: list[list[float]]
    row_draw_counts: list[int]


class BiasBacktest(BaseModel):
    """過去の各時点で、それ以前のデータだけを使った偏り検証"""

    evaluated_draws: int
    actual_average_score: float
    random_average_score: float
    score_lift_percent: float
    above_random_rate: float


class PredictResponse(BaseModel):
    lottery: LotteryType
    name: str                    # 表示名
    price: int                   # 1口の金額（円）
    next_round: int              # 予想の対象の回（集計した最後の回の次）
    sets: list[PredictedSet]     # 予想した番号の組
    total_draws: int             # 集計した回数
    first_date: datetime.date    # 集計した最初の抽選日
    last_date: datetime.date     # 集計した最後の抽選日
    last_round: int              # 集計した最後の回
    trend_metric: str            # 距離の種類
    trend_draw_count: int        # 傾向分析に使った全抽せん回数
    trend_first_date: datetime.date
    trend_last_date: datetime.date
    frequency_matrices: list[FrequencyMatrix]
    cooccurrence_matrices: list[CooccurrenceMatrix]
    prediction_method: str
    backtest: BiasBacktest
    model_version: str = "bias-v1"
