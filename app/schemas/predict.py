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


class AiPredictedSet(BaseModel):
    """AI に返してもらう番号1組"""

    numbers: list[int] = Field(description="選んだ番号。ナンバーズは左の桁から順に1桁ずつ")
    reason: str = Field(description="選んだ理由。集計結果の数字を使って日本語で100文字以内")


class PredictionOutput(BaseModel):
    """AI に返してもらう予想の形"""

    sets: list[AiPredictedSet] = Field(description="指定された組数ぶんの番号の組")
