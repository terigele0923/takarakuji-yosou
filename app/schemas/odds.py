from pydantic import BaseModel

from app.schemas.lottery import PlayType


class TierOdds(BaseModel):
    """1つの等級の当せん確率"""

    play_type: PlayType    # 申込タイプ
    tier: str              # 等級名
    probability: float     # 当せん確率
    odds_text: str         # 表示用（例：1/6,096,454、約1/39）
