import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import DB_PATH
from scripts.import_mizuho_data import (
    ParsedDraw,
    apply_records,
    compare_database,
    parse_bundle,
    parse_mizuho_csv,
)

OFFICIAL_ORIGIN = "https://www.mizuhobank.co.jp"
OFFICIAL_RESULTS_URL = f"{OFFICIAL_ORIGIN}/takarakuji/check/index.html"
MAX_ROUNDS_TO_SCAN = 100


@dataclass(frozen=True)
class CsvFamily:
    name: str
    prefix: str
    path: str
    lotteries: tuple[str, ...]

    def csv_url(self, round_number: int) -> str:
        filename = f"A{self.prefix}{round_number:04d}.CSV"
        return f"{OFFICIAL_ORIGIN}/retail/takarakuji/{self.path}/csv/{filename}"


CSV_FAMILIES = (
    CsvFamily("numbers", "100", "numbers", ("numbers3", "numbers4")),
    CsvFamily("miniloto", "101", "loto/miniloto", ("miniloto",)),
    CsvFamily("loto6", "102", "loto/loto6", ("loto6",)),
    CsvFamily("loto7", "103", "loto/loto7", ("loto7",)),
)


class LotteryDataConflictError(Exception):
    """Official data differs from an existing database record."""


class OfficialSiteError(Exception):
    """The official site could not be read through a browser."""


def import_official_bundle(payload: dict, db_path: Path = DB_PATH) -> tuple[int, int]:
    """Import a previously collected bundle for the command-line workflow."""
    return _store_records(parse_bundle(payload), db_path)


def update_latest_draws(
    db_path: Path = DB_PATH,
    browser_fetcher: Callable[[list[tuple[str, int, str]]], list[tuple[str, str]]] | None = None,
) -> tuple[int, int]:
    """Fetch and store only the latest official CSV for every lottery family."""
    latest_rounds = _database_latest_rounds(db_path)
    requests = [
        (family.name, latest_rounds[family.name], family.csv_url(latest_rounds[family.name]))
        for family in CSV_FAMILIES
    ]
    csv_files = (browser_fetcher or _fetch_latest_csvs_with_browser)(requests)
    records: list[ParsedDraw] = []
    for family, text in csv_files:
        records.extend(parse_mizuho_csv(family, text))
    return _store_records(records, db_path)


def _database_latest_rounds(db_path: Path) -> dict[str, int]:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    latest = {}
    with sqlite3.connect(db_path) as connection:
        for family in CSV_FAMILIES:
            marks = ",".join("?" for _ in family.lotteries)
            row = connection.execute(
                f"SELECT MAX(round) FROM draws WHERE lottery IN ({marks})", family.lotteries
            ).fetchone()
            if row is None or row[0] is None:
                raise ValueError(
                    f"{family.name} の基準データがDBにありません。先に過去データを登録してください"
                )
            latest[family.name] = int(row[0])
    return latest


def _fetch_latest_csvs_with_browser(
    requests: list[tuple[str, int, str]],
) -> list[tuple[str, str]]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise OfficialSiteError(
            "ブラウザー取得機能が未導入です。pip install playwright と playwright install chromium を実行してください"
        ) from error

    try:
        with sync_playwright() as playwright:
            # 公式サイトが自動HTTP取得を403にするため、通常表示のブラウザーを使う。
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            response = page.goto(OFFICIAL_RESULTS_URL, wait_until="domcontentloaded")
            if response is None or not response.ok:
                status = response.status if response else "応答なし"
                raise OfficialSiteError(f"みずほ銀行の公式ページを開けませんでした（{status}）")

            results = []
            for family_name, current_round, current_url in requests:
                latest_text = _browser_fetch_csv(page, current_url, required=True)
                family = next(item for item in CSV_FAMILIES if item.name == family_name)
                for offset in range(1, MAX_ROUNDS_TO_SCAN + 1):
                    candidate = _browser_fetch_csv(
                        page, family.csv_url(current_round + offset), required=False
                    )
                    if candidate is None:
                        break
                    latest_text = candidate
                else:
                    raise OfficialSiteError(
                        f"{family_name} はDBより{MAX_ROUNDS_TO_SCAN}回以上先です。過去データを更新してください"
                    )
                results.append((family_name, latest_text))
            browser.close()
            return results
    except OfficialSiteError:
        raise
    except PlaywrightError as error:
        raise OfficialSiteError(f"公式サイトのブラウザー取得に失敗しました: {error}") from error


def _browser_fetch_csv(page, url: str, required: bool) -> str | None:
    result = page.evaluate(
        """async ({url}) => {
          const response = await fetch(url, {credentials: "same-origin"});
          if (response.status === 404) return {status: 404, text: null};
          if (!response.ok) return {status: response.status, text: null};
          const bytes = await response.arrayBuffer();
          return {status: response.status, text: new TextDecoder("shift_jis").decode(bytes)};
        }""",
        {"url": url},
    )
    if result["status"] == 404 and not required:
        return None
    if result["status"] != 200:
        raise OfficialSiteError(f"公式CSVを取得できませんでした（HTTP {result['status']}）")
    return result["text"]


def _store_records(records: list[ParsedDraw], db_path: Path) -> tuple[int, int]:
    summary, conflicts = compare_database(db_path, records)
    if conflicts:
        raise LotteryDataConflictError("; ".join(conflicts[:20]))
    added_draws = summary["new_draws"]
    added_prizes = summary["new_prizes"]
    if added_draws or added_prizes:
        apply_records(db_path, records)
    return added_draws, added_prizes
