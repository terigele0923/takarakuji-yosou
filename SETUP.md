# 別の PC で動かす手順

このプロジェクトのフォルダを圧縮して、別の PC（自宅の個人 PC など）に置いて動かす手順。
上から順にコマンドをコピーして実行すれば移行できるように書いている。

- 使うのは Windows の PowerShell（VS Code のターミナル）。
- 各手順の「確認」に書いた結果にならなければ、先に進まずに末尾の「困ったとき」を見る。
- 会社の PC から個人の PC へファイルを持ち出す場合は、事前に会社のルールを確認する。

---

## A. 元の PC（会社の PC）でやること

### A-1. サーバーを止める

起動しているターミナルがあれば、すべてで `Ctrl + C` を押す（DB のファイルを使用中のままだと、圧縮に失敗することがある）。

### A-2. フォルダを圧縮する

VS Code のターミナルで、プロジェクトのフォルダ（`C:\Langchain_sample`）にいることを確かめてから実行する。
`.venv`（別の PC では動かない）とキャッシュを外して、デスクトップに `Langchain_sample.zip` を作る。

```powershell
cd C:\Langchain_sample
Get-ChildItem -Force -Exclude .venv, __pycache__, .pytest_cache | Compress-Archive -DestinationPath "$env:USERPROFILE\Desktop\Langchain_sample.zip" -Force
```

確認：

```powershell
Get-Item "$env:USERPROFILE\Desktop\Langchain_sample.zip" | Select-Object Name, Length
```

`Langchain_sample.zip` と大きさ（バイト数）が表示されればよい。

### A-3. zip を別の PC に移す

USB メモリなどで `Langchain_sample.zip` を別の PC に移す。
**zip には `.env`（API キー）が入っている**ので、メールや共有フォルダなど人目に触れる場所に置かない。

---

## B. 別の PC（自宅の PC）でやること

### B-1. Python が入っているか確かめる

PowerShell を開いて実行する。

```powershell
python --version
```

確認：`Python 3.10`〜`3.14`（推奨は3.14）が表示されればよい。Python 3.15では一部依存パッケージに対応ホイールがない場合がある。
`python` が見つからないときは `py --version` を試す。表示されたら、以下の `python` をすべて `py` に読み替える。

### B-2. zip を展開する

zip を「ダウンロード」フォルダに置いた場合の例。展開先は元の PC と同じ `C:\Langchain_sample` にする。

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\Langchain_sample.zip" -DestinationPath "C:\Langchain_sample"
```

確認：

```powershell
Get-ChildItem -Force C:\Langchain_sample | Select-Object Name
```

`app`、`data`、`scripts`、`tests`、`.env`、`requirements.txt`、`README.md`、`SETUP.md` などが表示されればよい。

### B-3. VS Code でフォルダを開く

VS Code の「ファイル」→「フォルダーを開く」で `C:\Langchain_sample` を開く。
そのあと「ターミナル」→「新しいターミナル」でターミナルを開く。以降はこのターミナルで実行する。

確認：ターミナルの行の先頭が `PS C:\Langchain_sample>` になっていればよい。

### B-4. 開発環境を準備する

仮想環境、Pythonパッケージ、ブラウザーを共通コマンドで準備する。

```powershell
.\scripts\dev.ps1 setup
```

確認：依存パッケージとChromiumのインストールがエラーなく終了すればよい。

### B-5. DBを最新構造にする

```powershell
.\scripts\dev.ps1 migrate
```

確認：エラーなく終了すればよい。既存データは保持され、未適用の変更だけが順番に適用される。

### B-6. VS Code に仮想環境を使わせる

`Ctrl + Shift + P` を押し、`Python: Select Interpreter`（Python: インタープリターを選択）を選んで、`.venv` と書かれたものを選ぶ。
これで、エディタ上のエラー表示やコードの移動（`Ctrl` + クリック）が正しく動く。

### B-7. テストで確かめる

```powershell
.\scripts\dev.ps1 verify
```

確認：最後に `passed` と表示され、`failed` がなければよい。

テストは除外オプションなしで全件実行する。公式CSV解析はアプリの共通サービスを直接テストし、CLI専用コードとWeb更新処理の重複を作らない構造になっている。

### B-8. API キーと DB を確かめる

API キーが `.env` に書かれているか（キーそのものは画面に出さない）。

```powershell
Select-String -Path .env -Pattern '^OPENAI_API_KEY=.+' -Quiet
```

確認：`True` と表示されればよい。`False` なら `.env` を開き、`OPENAI_API_KEY=` のあとに API キーを書く。

偏りモデルはサーバー起動中に既定24時間間隔で評価される。間隔を変える場合は `.env` に次を設定する。

```dotenv
MODEL_EVALUATION_ENABLED=true
MODEL_EVALUATION_INTERVAL_HOURS=24
```

新しい抽選結果がなければ再計算・重複保存はしない。手動で確認する場合は `.\scripts\dev.ps1 evaluate` を実行する。

現在のDBを壊さず、直近2か月を一回ずつ予想・答え合わせする検証は次で実行する。

```powershell
.\scripts\dev.ps1 walk-forward
```

結果は `data/walk_forward_report-日時.json`、検証用DBは `data/walk_forward_mock-日時.db` に保存される。

評価結果からナンバーズ3の重みを学習する場合は `.\scripts\dev.ps1 learn-model -Report "レポートのパス"` を実行する。学習済み重みはDBに保存され、次回以降の予想へ自動適用される。同じ2か月を再テストした値は学習済み期間の確認であり、未知期間に対する性能ではない。

外れを分析して5回改善する高度学習は `.\scripts\dev.ps1 advanced-learn -Loops 5` で実行する。2016〜2025年だけで改善し、2026年は最後の評価にしか使用しない。昇格条件を満たさない場合、本番モデルは自動更新されない。

評価用に収支へ取り込んだ購入だけを消して本番表示へ戻す場合は `.\scripts\dev.ps1 clear-test-purchases` を実行する。DBを自動バックアップした後、評価レポート由来の購入だけを削除し、通常の購入、抽選結果、賞金、学習履歴は保持する。

DBファイルが増えた場合は `.\scripts\dev.ps1 cleanup-db` を実行する。現在の本番DBから整合性確認済みバックアップを1個作成してから、古いバックアップと検証用モックDBを削除する。本番DB、サンプルDB、評価レポートは保持する。

DB に必要な表（抽選結果・賞金・購入の記録）があることを確認する。表の作成・更新はAlembicが行う。

```powershell
.\scripts\dev.ps1 migrate
```

確認：

```powershell
.venv\Scripts\python -c "import sqlite3; c = sqlite3.connect('data/lottery.db'); print(c.execute('SELECT lottery, COUNT(*) FROM draws GROUP BY lottery').fetchall()); print(c.execute('PRAGMA quick_check').fetchone())"
```

1行目に登録済みの種類別件数、2行目に `('ok',)` と表示されればよい。抽せん結果が空の場合は `LOTTERY_DATA_IMPORT.md` の手順で公式データを登録する。

### B-9. 起動する

プロジェクト専用のPythonから起動スクリプトを実行する。`uvicorn.exe` はWindowsセキュリティにブロックされる場合があるため直接実行しない。

```powershell
.\scripts\dev.ps1 run
```

確認：`Uvicorn running on http://127.0.0.1:8000` と `Application startup complete.` が表示されればよい。

### B-10. 画面で試す

ブラウザで http://localhost:8000 を開く。画面には「予想」「収支」「相談」の3つのタブがある。

1. **予想タブ**：種類と組数を選んで「予想する」を押す。長期頻度30%・時間加重直近頻度50%・ペア共起20%から作った候補、偏りスコア、時系列バックテスト、理論上の当せん確率が表示される。組ごとの「購入した」を押すと、次の回の購入として記録される
2. **収支タブ**：記録した購入と、使った金額・当たった金額・収支が表示される。この時点では結果は「未確認」。抽選日の開始・終了、回号、結果（当せん・外れ・未確認）で一覧と小計を絞り込める
3. 公式サイトで購入回の結果が公開されたら、予想タブの「最新情報を更新」を押す
4. **収支タブ**で「結果を確認」を押す。購入が「当せん」か「外れ」になり、当せん番号・賞金・収支が更新される
5. **相談タブ**：「ロト6の最近5回の結果は？」「偏りスコアは何を表す？」「私の収支は？」などを質問する

- 「予想する」はローカルの統計計算だけで、OpenAI APIを呼ばない。相談タブの「送信」はOpenAI APIを呼ぶため料金がかかる。
- 止めるときは、ターミナルで `Ctrl + C` を押す。

---

## 2回目からの起動

VS Code で `C:\Langchain_sample` を開き、新しいターミナルで実行する。

```powershell
.\scripts\dev.ps1 run
```

別のDBを使う場合の `$env:LOTTERY_DB_PATH` は、そのターミナルの中だけで有効。ターミナルを開き直したら、もう一度設定する。

---

## 困ったとき

| 症状 | 対処 |
|---|---|
| `Activate.ps1` が「このシステムではスクリプトの実行が無効」で止まる | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` を実行し、`Y` を押してから、B-4 の3行目をもう一度実行する |
| `python` が見つからない | `py --version` を試す。表示されたら `python` を `py` に読み替える。どちらも見つからなければ Python を入れ直す（インストール時に「Add python.exe to PATH」にチェックを入れる） |
| `Expand-Archive` で「既に存在します」と出る | 展開先に同じフォルダがある。中身を確かめて不要なら削除するか、`-Force` を付けて上書きする |
| `pip install` が失敗する | Python が 3.10 より古くないか確かめる（B-1） |
| 起動時に `OPENAI_API_KEY が設定されていません` | B-8 の API キーの確認を行う |
| 起動時に `Address already in use`（8000番が使用中） | ほかのターミナルでサーバーが動いていないか確かめて止める。またはコマンドの最後に `--port 8001` を付けて起動し、http://localhost:8001 を開く |
| 画面で「○○の抽選結果がまだありません」 | `data/lottery.db` にその種類の履歴がない。`LOTTERY_DATA_IMPORT.md` の手順で公式データを登録する |
| 画面で「抽選結果のデータベースが準備されていません」 | `data/lottery.db` がないか、表がない。B-8の表作成コマンドを実行する |
| 画面で「AIに接続できませんでした」 | API キーが正しいか、インターネットにつながっているか、OpenAI の利用残高があるかを確かめる |
| Mac で動かす | `.venv\Scripts\` を `.venv/bin/` に、`.venv\Scripts\Activate.ps1` を `source .venv/bin/activate` に、`$env:LOTTERY_DB_PATH = "data/sample.db"` を `export LOTTERY_DB_PATH=data/sample.db` に読み替える |

### DB の表を更新する

```powershell
.\scripts\dev.ps1 migrate
```

公式履歴の登録は `LOTTERY_DATA_IMPORT.md` を参照する。

---

## （任意）ブラウザの自動操作で公式ページを取得できるか試す

過去の抽選結果を公式ページ（みずほ銀行の過去当せん番号案内）から自動で取るための事前確認。
ロト6のページを2つ開き、`page0.html`・`page1.html` として保存するだけで、DB には何も書き込まない。

```powershell
.venv\Scripts\python -m pip install playwright
.venv\Scripts\python -m playwright install chromium
```

プロジェクトのフォルダに `probe.py` を作り、次の内容を書く。

```python
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(sys.argv[1])
urls = [
    "https://www.mizuhobank.co.jp/takarakuji/check/loto/backnumber/index.html",
    "https://www.mizuhobank.co.jp/takarakuji/check/loto/backnumber/loto60441.html",
]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    for i, url in enumerate(urls):
        resp = page.goto(url, wait_until="networkidle")
        print(resp.status, url, page.title())
        (out / f"page{i}.html").write_text(page.content(), encoding="utf-8")
        time.sleep(3)
    browser.close()
```

実行する（保存先は今のフォルダ）。

```powershell
.venv\Scripts\python probe.py .
```

| 結果 | 意味 |
|---|---|
| `200 https://...` が2行出る | この PC からは取得できる |
| `403` が出る | 公式ページから拒否されている（これ以上の回り道はしない） |
| ブラウザが起動の途中で終わる（`TargetClosedError`） | この PC でもブラウザの自動操作が止められている |
