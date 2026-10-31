from app.config import BASE_DIR

ANALYSIS_PROMPT_PATH = BASE_DIR / "prompts" / "lottery_analysis.md"


def load_analysis_prompt() -> str:
    """分析のたびに、プロジェクト内の分析ガイドを読み込む。"""
    try:
        content = ANALYSIS_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError(
            f"分析プロンプトを読み込めません: {ANALYSIS_PROMPT_PATH}"
        ) from error
    if not content:
        raise RuntimeError(f"分析プロンプトが空です: {ANALYSIS_PROMPT_PATH}")
    return content
