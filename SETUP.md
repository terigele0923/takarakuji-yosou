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

確認：`Python 3.10` 以上（例：`Python 3.14.0`）が表示されればよい。
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

### B-4. 仮想環境を作る

念のため古い `.venv` を消してから作り直す（ない場合も、エラーにならずに進む）。

```powershell
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv
.venv\Scripts\Activate.ps1
```

確認：ターミナルの行の先頭が `(.venv) PS C:\Langchain_sample>` になればよい。

### B-5. 必要なパッケージを入れる

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

確認：最後に `Successfully installed ...` と表示されればよい（数分かかることがある）。

### B-6. VS Code に仮想環境を使わせる

`Ctrl + Shift + P` を押し、`Python: Select Interpreter`（Python: インタープリターを選択）を選んで、`.venv` と書かれたものを選ぶ。
これで、エディタ上のエラー表示やコードの移動（`Ctrl` + クリック）が正しく動く。

### B-7. テストで確かめる

```powershell
.venv\Scripts\python -m pytest tests -q
```

確認：最後に `153 passed` のように表示され、`failed` がなければよい。

### B-8. API キーと DB を確かめる

API キーが `.env` に書かれているか（キーそのものは画面に出さない）。

```powershell
Select-String -Path .env -Pattern '^OPENAI_API_KEY=.+' -Quiet
```

確認：`True` と表示されればよい。`False` なら `.env` を開き、`OPENAI_API_KEY=` のあとに API キーを書く。

テスト用の DB に、必要な表（抽選結果・賞金・購入の記録）と仮の賞金をそろえる。
何度実行しても、今あるデータはそのまま残る（足りないものだけが足される）。

```powershell
.venv\Scripts\python -c "import sqlite3; sqlite3.connect('data/sample.db').executescript(open('scripts/create_tables.sql', encoding='utf-8').read())"
$env:LOTTERY_DB_PATH = "data/sample.db"
.venv\Scripts\python scripts/seed_sample_data.py
```

確認：

```powershell
.venv\Scripts\python -c "import sqlite3; c = sqlite3.connect('data/sample.db'); print(c.execute('SELECT lottery, COUNT(*) FROM draws GROUP BY lottery').fetchall()); print(c.execute('SELECT COUNT(DISTINCT lottery || round) FROM prizes').fetchone())"
```

1行目に `[('loto6', 500), ('loto7', 500), ('miniloto', 500), ('numbers3', 500), ('numbers4', 500)]`、2行目に `(2500,)` と表示されればよい。

### B-9. 起動する

2行とも、同じターミナルで実行する。

```powershell
$env:LOTTERY_DB_PATH = "data/sample.db"
.venv\Scripts\uvicorn app.main:app --reload
```

確認：`Uvicorn running on http://127.0.0.1:8000` と `Application startup complete.` が表示されればよい。

### B-10. 画面で試す

ブラウザで http://localhost:8000 を開く。画面には「予想」「収支」「相談」の3つのタブがある。

1. **予想タブ**：種類と組数を選んで「予想する」を押す。番号・理由・当せん確率が表示される。組ごとの「購入した」を押すと、次の回の購入として記録される
2. **収支タブ**：記録した購入と、使った金額・当たった金額・収支が表示される。この時点では結果は「未確認」
3. 購入した回の結果を作る（テスト用。今の回数が 500 なら 501 にする）。サーバーを動かしたまま、**別のターミナル**で実行する

   ```powershell
   $env:LOTTERY_DB_PATH = "data/sample.db"
   .venv\Scripts\python scripts/seed_sample_data.py --count 501
   ```

4. **収支タブ**で「結果を確認」を押す。購入が「当せん」か「外れ」になり、収支が更新される
5. **相談タブ**：「ロト6の最近5回の結果は？」「ロト7を毎週2口、1年買ったら収支はどうなりそう？」「私の収支は？」などを質問する

- 「予想する」と相談タブの「送信」は、OpenAI API が呼ばれて料金がかかる（1回で数回呼ぶことがある）。
- テスト用の DB の賞金は仮の金額で、本物ではない。
- 止めるときは、ターミナルで `Ctrl + C` を押す。

---

## 2回目からの起動

VS Code で `C:\Langchain_sample` を開き、新しいターミナルで実行する。

```powershell
$env:LOTTERY_DB_PATH = "data/sample.db"
.venv\Scripts\uvicorn app.main:app --reload
```

`$env:LOTTERY_DB_PATH` の切り替えは、そのターミナルの中だけで有効。ターミナルを開き直したら、もう一度実行する。

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
| 画面で「○○の抽選結果がまだありません」 | 起動したターミナルで `$env:LOTTERY_DB_PATH = "data/sample.db"` を実行していない、または別のサーバーにつながっている。すべてのサーバーを止めてから、B-9 をやり直す |
| 画面で「抽選結果のデータベースが準備されていません」 | `data/sample.db` がないか、表がない。下の「テスト用の DB を作り直す」を行う |
| 画面で「AIに接続できませんでした」 | API キーが正しいか、インターネットにつながっているか、OpenAI の利用残高があるかを確かめる |
| Mac で動かす | `.venv\Scripts\` を `.venv/bin/` に、`.venv\Scripts\Activate.ps1` を `source .venv/bin/activate` に、`$env:LOTTERY_DB_PATH = "data/sample.db"` を `export LOTTERY_DB_PATH=data/sample.db` に読み替える |

### テスト用の DB を作り直す

```powershell
# 表を作る（表がもうあれば table draws already exists と出るが、問題ない）
.venv\Scripts\python -c "import sqlite3; sqlite3.connect('data/sample.db').executescript(open('scripts/create_tables.sql', encoding='utf-8').read())"

# テスト用のデータを入れる（5種類 × 500回分。保存済みの回は飛ばす）
$env:LOTTERY_DB_PATH = "data/sample.db"
.venv\Scripts\python scripts/seed_sample_data.py
```

確認：「ロト6: 500件を保存しました」のような行が5種類分表示される（2回目以降は「0件」になる）。

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
