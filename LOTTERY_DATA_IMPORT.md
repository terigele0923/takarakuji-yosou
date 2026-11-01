# 公式の過去当せんデータをDBに取り込む

この文書では、みずほ銀行が公開している宝くじの当せんデータを集め、アプリの SQLite データベースに登録する仕組みを説明します。初めての人でも手順と各コマンドの意味がわかるように書いています。

## 何を取り込むか

みずほ銀行の「当せん番号案内」では、抽せん回ごとの CSV ファイルが公開されています。このプロジェクトでは、そこから抽せん日、本数字、ボーナス数字に加えて、等級ごとの当せん金額も取り込みます。

2026年10月31日に取得したデータは次のとおりです。

| 種類 | 回数 | 抽せん日の範囲 |
|---|---:|---|
| ナンバーズ3 | 3,871回 | 2011-10-31〜2026-10-30 |
| ナンバーズ4 | 3,871回 | 2011-10-31〜2026-10-30 |
| ミニロト | 773回 | 2011-11-01〜2026-10-27 |
| ロト6 | 1,548回 | 2011-10-31〜2026-10-29 |
| ロト7 | 701回 | 2013-04-05〜2026-10-30 |

ロト7は2013年に始まったため、15年分ではなく発売開始後の全データです。ナンバーズのCSVにはナンバーズ3と4の両方が含まれます。そのため、CSVファイルは6,893個ですが、抽せん結果は合計10,764件です。

## 使っているファイルと技術

| ファイル・技術 | 役割 |
|---|---|
| [scripts/mizuho_collect.js](./scripts/mizuho_collect.js) | ブラウザーから公式CSVを取得し、JSONファイルにまとめる JavaScript |
| [app/services/mizuho_import_service.py](./app/services/mizuho_import_service.py) | CSV解析、DB比較、バックアップ付き保存をWeb更新とCLIへ提供する共通サービス |
| [scripts/import_mizuho_data.py](./scripts/import_mizuho_data.py) | JSONファイル・引数を受け取り、共通サービスを呼び出すCLI入口 |
| [scripts/create_tables.sql](./scripts/create_tables.sql) | 抽せん結果・賞金・購入記録を保存する表の定義 |
| [migrations](./migrations) | 本番DBのスキーマ変更履歴。起動前にAlembicが未適用分を反映 |
| ブラウザーの `fetch` | 公式ページと同じ接続元からCSVを取得する機能 |
| `TextDecoder("shift_jis")` | 日本語の公式CSVを文字化けせず読み取るための変換 |
| SQLite | アプリが使うファイル型データベース |

ターミナルから公式CSVを直接取得すると、接続が拒否される場合があります。収集スクリプトは、みずほ銀行のページを開いたブラウザーからアクセスするため、この制限を避けて公式データを取得します。取得したデータはJSONにまとめてから検査し、抽せん番号を1件ずつ手入力する必要はありません。

## アプリ画面から最新情報をDBへ追加する

初回だけ、アプリが通常表示のブラウザーを起動できるように準備します。

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
```

準備後は、アプリの「予想」タブで「最新情報を更新」を押すだけです。通常表示のブラウザーがみずほ銀行の公式ページを開き、ナンバーズ3・4、ミニロト、ロト6、ロト7について最新回を確認します。サーバーから公式サイトへ直接HTTP接続すると403になるため、この更新処理は公式ページを開いたブラウザー内でCSVを取得します。

取得したCSVはサーバー側で検査し、DBにない最新回の抽せん結果・賞金だけを追加します。登録済みなら追加せず、既存データと内容が矛盾する場合は登録を中止します。追加前にはDBのバックアップも作成します。

更新された `draws` は、次回の予想から偏りモデルへ自動的に反映されます。長期頻度、半減期40回の時間加重直近頻度、番号ペア共起、時系列バックテストは予想リクエストごとに現在のDBから再計算されます。賞金の `prizes` は収支判定に使用し、予想番号の偏りスコアには使用しません。

## 取り込みの流れ

1. ブラウザーが、みずほ銀行の公式ページから抽せん回ごとのCSVを取得します。
2. 公式CSVをJSONファイルにまとめます。
3. PythonがCSVを解析し、抽せん日・番号・賞金を読み取ります。
4. 番号が宝くじのルールに合うか確認します（例：ミニロトの本数字は5個）。
5. データベースの既存データと比較します。内容の違う同じ回があれば、登録を中止して矛盾を表示します。
6. 問題がなければ、登録前にデータベースのバックアップを作成し、抽せん結果と賞金を追加します。

初期状態では「ドライラン」です。これは、本当に登録せず「何件追加されるか」を調べる確認運転です。`--apply` を付けた場合にだけデータベースへ書き込みます。

## 初めて実行するとき

以下は Windows PowerShell での手順です。コマンドを実行する前に、ターミナルの現在位置がプロジェクトフォルダー（例：`C:\Langchain_sample`）であることを確認してください。プロジェクトの準備が済んでいない場合は、先に [SETUP.md](./SETUP.md) の手順を行います。

### 1. 公式CSVを取得する

1. ブラウザーで[みずほ銀行の当せん番号案内](https://www.mizuhobank.co.jp/takarakuji/check/index.html)を開きます。
2. 開発者ツールを開きます（Windowsでは通常 `F12` キー）。「Console」タブを選びます。
3. プロジェクトにある `scripts/mizuho_collect.js` をテキストエディターで開き、内容をConsoleに貼り付けて実行します。
4. 確認メッセージが表示されたら、内容を確認して続行します。ブラウザーが複数ファイルのダウンロードを確認した場合は、許可します。
5. 処理が終わると `mizuho_lottery_history.json` がダウンロードされます。

この処理は大量の公式CSVを小分けに取得するため、数分以上かかることがあります。最新回は固定せず、公式CSVから検出します。実行中はConsoleに取得状況が表示されます。公式サイトに接続できない、または取得に失敗した場合、スクリプトはエラーを表示して停止します。

### 2. JSONをプロジェクト内に置く

ダウンロードしたJSONを、プロジェクト内の `data` フォルダーへコピーします。

```powershell
Copy-Item "$env:USERPROFILE\Downloads\mizuho_lottery_history.json" ".\data\mizuho_lottery_history.json"
```

「ファイルが見つからない」と表示された場合は、ブラウザーのダウンロード先を確認し、コマンド内の `Downloads` のパスを実際の保存場所に合わせてください。

### 3. ドライランで確認する

次のコマンドは、データを読み込んで件数と矛盾を確認します。データベースは変更しません。

```powershell
.venv\Scripts\python scripts\import_mizuho_data.py data\mizuho_lottery_history.json --db data\lottery.db
```

表示される `Database:` が `data\lottery.db` であること、宝くじごとの回数が想定どおりであることを確認します。問題のないデータを初めて登録する場合は、`Conflicts: 0`（または矛盾表示がないこと）を確認します。最後に `Dry run only. No database changes were made.` と表示されるのは正常です。

### 4. データベースへ登録する

ドライランの対象DBと件数を確認したあとで、同じコマンドに `--apply` を付けて実行します。

```powershell
.venv\Scripts\python scripts\import_mizuho_data.py data\mizuho_lottery_history.json --db data\lottery.db --apply
```

実行結果に `Imported successfully.` とバックアップファイルの場所が表示されれば登録完了です。バックアップは `data\lottery.backup-日時.db` という名前で作られます。初回登録時の例は `lottery.backup-20261031-114347.db` です。

同じJSONを再度取り込んでも、同じ回の抽せん結果・賞金を重複登録しません。再実行前にドライランすると、登録済み件数が `existing` に表示され、`new` は0件になります。

## 登録後の確認

次のコマンドを実行すると、抽せん結果と賞金の件数を確認できます。

```powershell
.venv\Scripts\python -c "import sqlite3; c=sqlite3.connect('data/lottery.db'); print('draws:', c.execute('SELECT lottery, COUNT(*) FROM draws GROUP BY lottery ORDER BY lottery').fetchall()); print('prizes:', c.execute('SELECT lottery, COUNT(*) FROM prizes GROUP BY lottery ORDER BY lottery').fetchall()); print('integrity:', c.execute('PRAGMA quick_check').fetchone()[0]); c.close()"
```

`integrity: ok` と表示されることを確認してください。購入記録は `purchases` 表に別途保存され、過去データの取り込みでは変更されません。

## よくある問題

### `HTTP 403` やアクセス拒否になる

ターミナルからCSVを直接取得している可能性があります。収集スクリプトは、みずほ銀行の公式ページをブラウザーで開いた状態で実行してください。

### `mizuho_lottery_history.json` が見つからない

ブラウザーがダウンロードをブロックしていないか確認します。ブラウザーのダウンロード一覧で保存場所を確認し、プロジェクトの `data` フォルダーにコピーしてください。複数ダウンロードの許可を求められた場合は許可します。

### ドライランで `Database is missing required tables` と表示される

対象DBに必要な表がありません。まずDBファイルのパスが正しいか確認します。表を新規作成・更新する場合は、プロジェクトのルートで次を実行します。

```powershell
.\scripts\dev.ps1 migrate
```

Alembicは未適用の変更だけを順番に反映します。`LOTTERY_DB_PATH` を指定している場合は、そのDBが対象になるため実行前にパスを確認してください。

### `Conflicts` が表示される

同じ宝くじの同じ回について、DB内の番号・日付または賞金が公式CSVと異なっています。安全のため自動上書きはせず、取り込みを中止します。矛盾内容と対象DBを確認し、原因がわかるまで `--apply` を実行しないでください。

### `No JSON bundles found` または `No CSV files found`

指定したJSONの場所が違うか、JSONのダウンロードが完了していません。`Get-Item .\data\mizuho_lottery_history.json` でファイルがあることを確認してから再実行します。

## 安全上の注意

- `data\lottery.db` はアプリが使うDBです。`data\sample.db` はテスト用データのため、実データの登録先にしないでください。
- `--apply` を付ける前に、ドライランでDBのパス・件数・矛盾の有無を確認してください。
- 登録前の自動バックアップも残してください。バックアップはDBの復旧に必要になる場合があります。
- 取り込むのは公開されている当せん番号と賞金データです。宝くじの購入履歴や個人情報を取得する処理ではありません。
