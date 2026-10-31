import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.lottery import LotteryType, PlayType


class PurchaseRequest(BaseModel):
    lottery: LotteryType
    round: int = Field(ge=1)    # 買った回
    numbers: list[int]          # 予想した番号（ミニもナンバーズ3の3桁で受け取る）
    play_type: PlayType         # 申込タイプ


class PurchaseResponse(BaseModel):
    id: int
    lottery: LotteryType
    round: int
    numbers: list[int]          # 記録した番号（ミニは下2桁）
    play_type: PlayType
    price: int                  # 金額（円）
    purchased_at: datetime.datetime


class PurchaseStatus(str, Enum):
    """購入した番号の結果"""

    PENDING = "pending"              # その回の抽選結果がまだない
    WON = "won"                      # 当せん
    LOST = "lost"                    # 外れ
    PRIZE_UNKNOWN = "prize_unknown"  # 当せんしたが、賞金がまだ DB にない


class PurchaseRecord(PurchaseResponse):
    """収支の一覧に出す、購入1件分"""

    name: str                           # 宝くじの表示名
    status: PurchaseStatus
    tier: str | None                    # 当たった等級
    prize: int | None                   # 当たった金額（未確認は None、外れは 0）
    winning_numbers: list[int] | None   # その回の本数字（結果未公開なら None）
    bonus_numbers: list[int] | None     # その回のボーナス数字（結果未公開なら None）
    expected_return: float | None       # 期待される戻り（当せん確率 × 平均の賞金。賞金のデータがなければ None）


class PurchaseSummary(BaseModel):
    """購入全体の収支"""

    count: int                  # 購入した件数
    spent: int                  # 使った金額
    won: int                    # 当たった金額
    profit: int                 # 収支（当たった金額 − 使った金額）
    pending_count: int          # 結果がまだの件数
    expected_return: float      # 期待される戻りの合計
    expected_is_partial: bool   # 賞金のデータがなく、期待される戻りに含められなかった購入があるか


class PurchaseListResponse(BaseModel):
    purchases: list[PurchaseRecord]   # 新しい順
    summary: PurchaseSummary


class PurchaseCheckResponse(PurchaseListResponse):
    """結果確認後の一覧と、今回新しく判定できた件数"""

    checked_count: int
