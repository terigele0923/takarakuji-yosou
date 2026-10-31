# 宝くじ予想AI

過去の抽選番号をもとに、LangChain と OpenAI のモデルで次の番号を予想し、購入の収支を記録するアプリ。

| タブ | できること |
|---|---|
| 予想 | 種類と組数（1〜10組）を選ぶと、AI が番号を選び、過去結果とのベクトル距離で候補を順位付けする。番号の出現回数・ペア分析と理論上の当せん確率を表示する。「購入した」で購入を記録する |
| 収支 | 購入の一覧と、使った金額・当たった金額・収支・期待される戻りを表示する。「結果を確認」で抽選結果と照らし合わせる |
| 相談 | AI エージェント（LangChain の `create_agent`）に自由に質問できる。抽選結果・集計・当せん確率・収支・購入の試算の道具を、AI が自分で選んで使う |

抽選は毎回ランダムで、どの番号を選んでも当せん確率は変わらない。予想は参考情報。
傾向スコア・番号の出現頻度・ペア割合は過去データの分析であり、次回の当せん確率を高めるものではない。

別の PC で動かす手順は `SETUP.md` を参照。
公式の過去当せんデータを取得・登録する仕組みは `LOTTERY_DATA_IMPORT.md` を参照。
予想と相談AIが参照する分析上の注意点・公開資料は `prompts/lottery_analysis.md` にまとめており、分析リクエストのたびに読み込みます。

## 構成

| 場所 | 役割 |
|---|---|
| `app/main.py` | 起動の入口（FastAPI の作成、画面の配信） |
| `app/config.py` | 設定（.env の読み込み、モデル名） |
| `app/api/` | API の受け口 |
| `app/schemas/` | 入力と出力の型 |
| `app/services/` | 処理（LangChain の呼び出しなど） |
| `app/static/` | 画面（HTML・CSS・JS） |
| `prompts/lottery_analysis.md` | 予想・相談AIが毎回参照する分析ルールと出典 |
| `app/db.py` | SQLite への接続 |
| `data/` | 本物の DB（lottery.db）、テスト用の DB（sample.db） |
| `scripts/` | 表を作る SQL、テスト用データの作成、動作確認用のスクリプト |
| `tests/` | テスト |

## データ（data/lottery.db）

SQLite の `data/lottery.db` に、次の3つの表を持つ。表の定義は `scripts/create_tables.sql`。

| 表 | 中身 |
|---|---|
| `draws` | 過去の抽選結果（種類と回で1行） |
| `prizes` | 回ごと・等級ごとの1口あたりの賞金 |
| `purchases` | 購入した記録（申込タイプ・結果の等級・当たった金額） |

環境変数 `LOTTERY_DB_PATH` で、使う DB を変えられる（例：テスト用の `data/sample.db`）。

### 抽選結果（draws）の番号

| `lottery` の値 | 種類 | 本数字 | ボーナス数字 |
|---|---|---|---|
| `numbers3` | ナンバーズ3 | 0〜9 を3桁（重複あり） | なし |
| `numbers4` | ナンバーズ4 | 0〜9 を4桁（重複あり） | なし |
| `miniloto` | ミニロト | 1〜31 から5個 | 1個 |
| `loto6` | ロト6 | 1〜43 から6個 | 1個 |
| `loto7` | ロト7 | 1〜37 から7個 | 2個 |

`numbers`・`bonus` 列はカンマ区切り（例：`1,5,12,19,30,41`）。

### 申込タイプ（purchases の play_type）

| 値 | 意味 | 対象 |
|---|---|---|
| `normal` | 通常 | ミニロト・ロト6・ロト7 |
| `straight` | ストレート（数字と並び順が一致） | ナンバーズ3・4 |
| `box` | ボックス（並び順は問わない。ゾロ目は不可） | ナンバーズ3・4 |
| `set` | セット（ストレートとボックスを半分ずつ。ゾロ目は不可） | ナンバーズ3・4 |
| `mini` | ミニ（下2桁の数字と並び順が一致） | ナンバーズ3 |

## 準備

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # .env に OPENAI_API_KEY を書く

# 表を作る（何度実行しても、今あるデータはそのまま残る）
python -c "import sqlite3; sqlite3.connect('data/lottery.db').executescript(open('scripts/create_tables.sql', encoding='utf-8').read())"
```

## 起動

```powershell
uvicorn app.main:app --reload
```

- 画面：http://localhost:8000
- API の確認画面：http://localhost:8000/docs

テスト用の DB で試す場合：

```powershell
$env:LOTTERY_DB_PATH = "data/sample.db"
python scripts/seed_sample_data.py            # 5種類 × 500回分の抽選結果と仮の賞金を作る
uvicorn app.main:app --reload
```

`seed_sample_data.py --count 501` のように回数を増やすと、増えた回の結果だけが足される（購入した回の結果を作って、収支タブの「結果を確認」を試せる）。

## テスト

```powershell
python -m pytest tests -q
```
