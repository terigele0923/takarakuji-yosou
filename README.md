# 宝くじ予想AI

過去の抽せん番号に現れた長期・直近・番号ペアの偏りを数値化して次回候補を作り、購入の収支を記録するアプリ。OpenAI は相談タブで使用するが、予想番号そのものは統計アルゴリズムが生成する。

| タブ | できること |
|---|---|
| 予想 | 種類と組数（1〜10組）を選ぶと、長期頻度・時間加重した直近頻度・番号ペア共起から候補を生成する。偏り予測スコア、内訳、時系列バックテスト、理論上の当せん確率を表示する。「購入した」で購入を記録する |
| 収支 | 購入の一覧と、使った金額・当たった金額・収支・期待される戻りを表示する。「結果を確認」で抽選結果と照らし合わせ、抽選日の範囲・回号・当せん状態で絞り込める |
| 相談 | AI エージェント（LangChain の `create_agent`）に自由に質問できる。抽選結果・集計・当せん確率・収支・購入の試算の道具を、AI が自分で選んで使う |

このアプリは「過去データに偏りがあり、その一部が将来にも継続する」という予測仮説を採用する。偏り予測スコアは理論上の当せん確率ではなく、保存済みデータに対するモデル適合度である。時系列バックテストで、実結果のスコアが同時点のランダム候補をどの程度上回ったかを併記する。

別の PC で動かす手順は `SETUP.md` を参照。
公式の過去当せんデータを取得・登録する仕組みは `LOTTERY_DATA_IMPORT.md` を参照。
相談AIが参照する分析ルールと予測モデルの解釈は `prompts/lottery_analysis.md` にまとめており、相談リクエストのたびに読み込みます。

## 偏り予測モデル

予想のデータフローは次のとおり。

`drawsテーブル → 長期頻度 → 時間加重直近頻度 → ペア共起 → 平滑化 → 候補探索 → 分散選択 → 時系列バックテスト → API/画面`

- 長期頻度30%：保存されている全期間の番号別・桁別出現率
- 直近頻度50%：半減期40回で、最近の抽せんほど大きな重みを付けた出現率
- ペア共起20%：ロト系は本数字ペア、ナンバーズ系は桁間の数字ペア
- 平滑化：少数回の偶然を極端な偏りとして扱わないよう、期待頻度を事前値として加える
- 候補探索：ナンバーズは全組み合わせ、ロト系はビーム探索で高スコア候補を探す
- 分散選択：複数組が同じ番号に集中しすぎないよう、候補間の重複を制限する
- バックテスト：直近最大40回について、その回より前のデータだけでモデルを作り、実結果とランダム候補200組のスコアを比較する

偏り予測スコアは `0〜100` の相対的なモデルスコアであり、当せん確率の百分率ではない。DBが同じなら同じ計算結果を再現する。

## 予想履歴と偏りモデルの定期評価

予想結果と評価指標はDBに履歴として保存する。

- 予想保存：`予想ボタン → POST /api/predict → 偏りモデル → prediction_runs → API/画面`
- 定期評価：`サーバー起動・24時間間隔・抽選データ更新 → 未評価の最終回を検出 → 時系列バックテスト → model_evaluations`

同じ宝くじ種類・最終抽選回・モデル版の評価は一度だけ保存する。新しい抽選結果が入ると新しい評価行を作成する。評価間隔は `.env` の `MODEL_EVALUATION_INTERVAL_HOURS` で変更でき、`MODEL_EVALUATION_ENABLED=false` で停止できる。

手動で即時評価する場合：

```powershell
.\scripts\dev.ps1 evaluate
```

保存結果はAPIでも確認できる。

- `GET /api/predictions?lottery=loto6&limit=20`
- `GET /api/model-evaluations?lottery=loto6&limit=20`

## 直近2か月のウォークフォワードテスト

実DBを変更せず、コピーしたモックDBを2か月前へ戻して、各抽選回を未来データとして1件ずつ開示するテストを実行できる。

`実DBコピー → 2か月分のdrawsを保留 → 直前までのデータで予想 → 次の当選番号を1件追加 → 一致数評価 → 次の回へ`

```powershell
.\scripts\dev.ps1 walk-forward
```

既定では1回につき1組を予想し、同じ口数のランダム候補200回分と平均一致数を比較する。組数や期間を変える場合：

```powershell
.\scripts\dev.ps1 walk-forward -Months 2 -Count 5 -RandomSamples 500
```

実行ごとに時刻付きの `data/walk_forward_mock-*.db` と `data/walk_forward_report-*.json` を新規作成する。JSONには各回の予想番号、偏りスコア、当選番号、本数字・ボーナス一致数、完全一致、ランダム平均と、種類別集計を保存する。

前回の評価期間からナンバーズ3の長期・直近・ペア重みを学習する場合：

```powershell
.\scripts\dev.ps1 learn-model -Report "data\walk_forward_report-日時.json"
```

学習処理は重みを10%刻みで比較し、各回5セット中の完全一致、2桁以上一致、合計一致数の順に良い設定を `bias_model_profiles` へ保存する。その後の画面予想、相談AI、定期評価、ウォークフォワード評価は保存済み重みを使う。同じ期間を学習と評価の両方に使った結果は独立検証ではなく、学習期間への適合結果である。

### 外れフィードバックの5回反復学習

より厳密な学習は次で実行する。

```powershell
.\scripts\dev.ps1 advanced-learn -Loops 5
```

データの流れは次のとおり。

`2016〜2025年 → 5セット予想 → ストレート外れを抽出 → 周辺の重み・半減期を比較 → 改善設定で次ループ（5回） → 完全未使用の2026年で現行モデルと比較 → 合格時だけ本番昇格`

各ループは長期・直近・ペア重みを5%ずつ移動し、半減期10・20・40・80・160回の隣接候補も比較する。完全一致、外れ回の2桁一致、合計一致数、全1,000通り中の当せん番号順位の順に改善設定を選ぶ。

2026年の最終評価では、候補モデルが現行モデルより平均順位で良く、平均順位が500位より上で、ランダム5セットとの差の95%信頼区間下限が0より大きい場合だけ `bias_model_profiles` を更新する。不合格の候補も `model_training_runs` と `data/advanced_training_report-*.json` に監査履歴として残す。

評価結果を収支へ反映する場合は次を実行する。ナンバーズ3は既定で各回ストレート5口、ほかはレポートに保存された予想数を登録する。実行前にDBを自動バックアップし、同じレポートの二重登録は行わない。

```powershell
.\scripts\dev.ps1 import-walk-forward -Report "data\walk_forward_report-日時.json" -Numbers3Tickets 5
```

前回取り込んだテスト購入を削除して新しいレポートへ置き換える場合は `-ReplaceExisting` を付ける。手入力・画面登録した通常の購入は削除しない。

## 構成

| 場所 | 役割 |
|---|---|
| `app/main.py` | 起動の入口（FastAPI の作成、画面の配信） |
| `app/config.py` | 設定（.env の読み込み、モデル名） |
| `app/api/` | API の受け口 |
| `app/schemas/` | 入力と出力の型 |
| `app/services/` | 偏り予測、集計、購入判定、LangChain相談などの処理 |
| `app/services/mizuho_import_service.py` | 公式CSVの解析・DB比較・バックアップ付き保存。Web更新とCLIで共用 |
| `app/utils/` | 番号配列のDB文字列変換など、業務ルールを持たない共通処理 |
| `app/static/` | 画面（HTML・CSS・JS） |
| `prompts/lottery_analysis.md` | 予想・相談AIが毎回参照する分析ルールと出典 |
| `app/db.py` | SQLite への接続 |
| `app/db_migrations.py` | Alembicマイグレーションの実行入口 |
| `data/` | 本物の DB（lottery.db）、テスト用の DB（sample.db） |
| `migrations/` | DBスキーマの変更履歴（Alembic） |
| `scripts/dev.ps1` | セットアップ、検査、テスト、DB更新、起動をまとめた開発コマンド |
| `.github/workflows/ci.yml` | push・Pull Request時に自動検証するGitHub Actions |
| `tests/` | テスト |

## データ（data/lottery.db）

SQLite の `data/lottery.db` に、次の5つの表を持つ。スキーマの正本は `migrations/` の変更履歴で、`scripts/create_tables.sql` はテスト用DBを素早く作るためにも使用する。

| 表 | 中身 |
|---|---|
| `draws` | 過去の抽選結果（種類と回で1行） |
| `prizes` | 回ごと・等級ごとの1口あたりの賞金 |
| `purchases` | 購入した記録（申込タイプ・結果の等級・当たった金額） |
| `prediction_runs` | 生成時刻、対象回、使用データの最終回、予想APIの全出力 |
| `model_evaluations` | データ最終回ごとのバックテスト指標とモデル版 |

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
.\scripts\dev.ps1 setup
copy .env.example .env   # .env に OPENAI_API_KEY を書く
.\scripts\dev.ps1 migrate
```

## 起動

```powershell
.\scripts\dev.ps1 run
```

起動時は `開発コマンド → run_server.py → Alembic → data/lottery.db → FastAPI` の順に進み、未適用のDB変更を適用してからサーバーを公開する。

- 画面：http://localhost:8000
- API の確認画面：http://localhost:8000/docs

別のDBを試す場合は、`LOTTERY_DB_PATH` を設定してから同じ起動スクリプトを実行する。

## テスト

```powershell
.\scripts\dev.ps1 verify
```

`verify` は Ruff、JavaScript構文確認、一時DBへのマイグレーション、全テスト、Python構文確認を順番に実行する。GitHub Actionsも同じコマンドを使うため、ローカルとCIの判定が一致する。

主な開発コマンドは `setup`、`run`、`migrate`、`test`、`lint`、`format`、`verify`。一覧は `.\scripts\dev.ps1 help` で確認できる。
