import functools
import json
import sqlite3

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from app.config import MODEL_NAME
from app.schemas.lottery import LOTO_TIERS, RULES, LotteryType, PlayType
from app.services.lottery_data import load_average_prizes, load_draw, load_draws
from app.services.odds_service import calculate_odds
from app.services.predict_service import predict
from app.services.prompt_loader import load_analysis_prompt
from app.services.purchase_service import expected_return, list_purchases
from app.services.stats_service import calculate_stats
from app.services.trend_service import build_history_matrices

SYSTEM_PROMPT = (
    "あなたは宝くじアプリのアシスタントです。"
    "抽選結果・集計・当せん確率・購入の収支などの数字は、必ず道具（ツール）を使って調べ、"
    "道具の結果だけをもとに答えてください。数字を推測で作ってはいけません。"
    "番号頻度やペアの傾向を質問されたら、全期間の履歴分析ツールを使ってください。"
    "このアプリは、過去の偏りの一部が未来にも継続するという仮説で候補を生成します。"
    "偏り予測スコア、理論確率、時系列バックテスト実績を区別し、結果を保証しないでください。"
    "金額は円で、日本語で簡潔に答えてください。"
)

# 一度に返す抽選結果の数の上限
MAX_RECENT_DRAWS = 20


def _to_json(value) -> str:
    """道具の結果を、AI が読みやすい JSON の文字にする"""
    return json.dumps(value, ensure_ascii=False, default=str)


def _db_guard(func):
    """DB が準備されていないときは、エラーではなくその旨の文字を返す"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (FileNotFoundError, sqlite3.OperationalError):
            return "抽選結果のデータベースが準備されていません。"
    return wrapper


@tool
def lottery_rules() -> str:
    """5種類の宝くじ（ナンバーズ3・4、ミニロト、ロト6・7）のルール・1口の金額・申込タイプ・等級の条件を返す。"""
    rules = []
    for lottery, rule in RULES.items():
        item = {
            "lottery": lottery.value,
            "name": rule.name,
            "price": rule.price,
            "play_types": [play.value for play in rule.play_types],
            "numbers": f"{rule.min}〜{rule.max}から{rule.count}個"
            + ("（桁ごと、同じ数字も可）" if rule.by_position else "（重複なし）"),
            "bonus_count": rule.bonus_count,
        }
        if lottery in LOTO_TIERS:
            item["tiers"] = [
                {"tier": tier.name, "matches": tier.matches, "bonus": tier.bonus}
                for tier in LOTO_TIERS[lottery]
            ]
        rules.append(item)
    return _to_json(rules)


@tool
@_db_guard
def recent_draws(lottery: LotteryType, count: int = 10) -> str:
    """指定した宝くじの、最近の抽選結果を新しい順に返す（count は最大20）。"""
    draws = load_draws(lottery)[-min(max(count, 1), MAX_RECENT_DRAWS):]
    return _to_json([draw.model_dump() for draw in reversed(draws)])


@tool
@_db_guard
def draw_result(lottery: LotteryType, round: int) -> str:
    """指定した宝くじ・回の抽選結果（当せん番号とボーナス数字）を返す。"""
    draw = load_draw(lottery, round)
    if draw is None:
        return f"{RULES[lottery].name}の第{round}回の抽選結果はまだありません。"
    return _to_json(draw.model_dump())


@tool
@_db_guard
def number_stats(lottery: LotteryType, top: int = 10) -> str:
    """直近10年分の集計から、よく出ている番号と、しばらく出ていない番号を返す（ナンバーズは桁ごと）。"""
    stats = calculate_stats(lottery, load_draws(lottery))
    if stats.total_draws == 0:
        return f"{RULES[lottery].name}の抽選結果がまだありません。"
    positions = []
    for numbers in stats.positions:
        positions.append({
            "most_frequent": [
                stat.model_dump() for stat in sorted(numbers, key=lambda s: -s.count)[:top]
            ],
            "longest_gap": [
                stat.model_dump()
                for stat in sorted(numbers, key=lambda s: -(s.gap if s.gap is not None else 10**9))[:top]
            ],
        })
    return _to_json({
        "name": RULES[lottery].name,
        "period": f"{stats.first_date}〜{stats.last_date}",
        "total_draws": stats.total_draws,
        "note": "gap は最後に出てから何回たったか。ナンバーズは左の桁から順",
        "positions": positions,
    })


@tool
@_db_guard
def historical_pattern_analysis(lottery: LotteryType) -> str:
    """保存されている全期間の番号出現回数と、番号ペア・桁位置ペアの同時出現回数と条件付き割合を返す。"""
    draws = load_draws(lottery)
    if not draws:
        return f"{RULES[lottery].name}の抽選結果がまだありません。"
    frequencies, cooccurrences = build_history_matrices(lottery, draws)
    return _to_json({
        "name": RULES[lottery].name,
        "period": f"{min(draw.draw_date for draw in draws)}〜{max(draw.draw_date for draw in draws)}",
        "total_draws": len(draws),
        "frequency_matrices": [matrix.model_dump() for matrix in frequencies],
        "cooccurrence_matrices": [matrix.model_dump() for matrix in cooccurrences],
        "note": "条件付き割合は過去の実績であり、次回の当選確率ではない。",
    })


@tool
def winning_odds(lottery: LotteryType, numbers: list[int]) -> str:
    """番号1組の、申込タイプ・等級ごとの当せん確率を返す。"""
    try:
        odds = calculate_odds(lottery, numbers)
    except (ValueError, IndexError, KeyError):
        return "番号がルールに合っていません。"
    return _to_json([item.model_dump() for item in odds])


@tool
@_db_guard
def bias_prediction(lottery: LotteryType, count: int = 3) -> str:
    """長期頻度・時間加重直近頻度・ペア共起の偏りから候補を作り、スコア内訳と時系列バックテストを返す。"""
    result = predict(lottery, min(max(count, 1), 10))
    return _to_json({
        "name": result.name,
        "next_round": result.next_round,
        "method": result.prediction_method,
        "sets": [
            {
                "rank": item.rank,
                "numbers": item.numbers,
                "bias_score": item.bias_score,
                "bias_components": item.bias_components,
                "reason": item.reason,
            }
            for item in result.sets
        ],
        "backtest": result.backtest.model_dump(),
    })


@tool
@_db_guard
def purchase_summary() -> str:
    """利用者がこのアプリで記録した購入の収支の合計と、最近10件の購入を返す。"""
    result = list_purchases()
    return _to_json({
        "summary": result.summary.model_dump(),
        "recent_purchases": [record.model_dump() for record in result.purchases[:10]],
    })


@tool
@_db_guard
def cost_simulation(lottery: LotteryType, tickets_per_draw: int, draws: int) -> str:
    """毎回 tickets_per_draw 口を draws 回買ったときの、使う金額・期待される戻り・期待される収支を計算する。
    ナンバーズはストレートで買う場合として計算する。期待される戻りは、当せん確率とこれまでの平均の賞金から計算する。"""
    rule = RULES[lottery]
    play_type = PlayType.STRAIGHT if rule.by_position else PlayType.NORMAL
    sample_numbers = list(range(1, rule.count + 1))
    per_ticket = expected_return(lottery, play_type, sample_numbers, load_average_prizes(lottery))
    if per_ticket is None:
        return f"{rule.name}の賞金のデータが足りないため、期待される戻りを計算できません。"
    tickets = tickets_per_draw * draws
    cost = rule.price * tickets
    returned = per_ticket * tickets
    return _to_json({
        "name": rule.name,
        "tickets": tickets,
        "cost": cost,
        "expected_return": round(returned),
        "expected_profit": round(returned - cost),
        "return_rate": round(per_ticket / rule.price, 3),
    })


TOOLS = [
    lottery_rules,
    recent_draws,
    draw_result,
    number_stats,
    historical_pattern_analysis,
    winning_odds,
    bias_prediction,
    purchase_summary,
    cost_simulation,
]

_checkpointer = InMemorySaver()


@functools.lru_cache(maxsize=1)
def get_agent(analysis_prompt: str):
    """道具と会話の記憶を持つエージェントを作る（1回だけ作って使い回す）"""
    return create_agent(
        model=ChatOpenAI(model=MODEL_NAME),
        tools=TOOLS,
        system_prompt=f"{SYSTEM_PROMPT}\n\n{analysis_prompt}",
        checkpointer=_checkpointer,
    )


def ask(message: str, thread_id: str) -> str:
    """エージェントに質問し、最後の返答の文章を返す（同じ thread_id なら前のやり取りを覚えている）"""
    result = get_agent(load_analysis_prompt()).invoke(
        {"messages": [{"role": "user", "content": message}]},
        {"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].text
