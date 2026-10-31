import datetime

from pydantic import BaseModel

from app.schemas.lottery import LotteryType


class NumberStat(BaseModel):
    """1つの番号（ナンバーズは1つの桁の数字）の集計"""

    number: int        # 番号
    count: int         # 出た回数
    gap: int | None    # 最後に出てから何回たったか（0 は最新の回に出た。一度も出ていなければ None）


class LotteryStats(BaseModel):
    """宝くじ1種類分の集計結果"""

    lottery: LotteryType
    total_draws: int                      # 集計した回数
    first_date: datetime.date | None      # 集計した最初の抽選日
    last_date: datetime.date | None       # 集計した最後の抽選日
    last_round: int | None                # 集計した最後の回
    positions: list[list[NumberStat]]     # ロト系は全体で1つ、ナンバーズは桁ごと（左の桁から）
