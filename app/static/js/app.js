const form = document.getElementById("predict-form");
const lotterySelect = document.getElementById("lottery");
const countSelect = document.getElementById("count");
const predictButton = document.getElementById("predict-button");
const updateDataButton = document.getElementById("update-data-button");
const updateDataStatus = document.getElementById("update-data-status");
const updateDataError = document.getElementById("update-data-error");
const errorArea = document.getElementById("error");
const resultArea = document.getElementById("result");
const resultTitle = document.getElementById("result-title");
const resultPeriod = document.getElementById("result-period");
const commonOdds = document.getElementById("common-odds");
const commonOddsTable = document.getElementById("common-odds-table");
const resultSets = document.getElementById("result-sets");
const trendDescription = document.getElementById("trend-description");
const trendMatrix = document.getElementById("trend-matrix");
const frequencyMatrices = document.getElementById("frequency-matrices");
const cooccurrenceMatrices = document.getElementById("cooccurrence-matrices");

// 一度に予想できる組数の上限（API の MAX_SETS と同じ）
const MAX_SETS = 10;

// 申込タイプの表示名
const PLAY_TYPE_NAMES = {
  normal: "通常",
  straight: "ストレート",
  box: "ボックス",
  set: "セット",
  mini: "ミニ（下2桁）",
};

// エラーを表示する
function showError(message) {
  errorArea.textContent = message;
  errorArea.hidden = false;
}

// エラーの応答から、表示するメッセージを取り出す
async function errorMessage(response) {
  const error = await response.json().catch(() => ({}));
  return typeof error.detail === "string"
    ? error.detail
    : "処理に失敗しました（" + response.status + "）";
}

// 指定したタグの要素を作り、文字を入れて返す
function createElement(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

// 等級ごとの当せん確率の表を作る
function fillOddsTable(table, odds, withPlayType) {
  const header = table.insertRow();
  if (withPlayType) header.appendChild(createElement("th", "申込タイプ"));
  header.appendChild(createElement("th", "等級"));
  header.appendChild(createElement("th", "当せん確率"));
  for (const item of odds) {
    const row = table.insertRow();
    if (withPlayType) row.insertCell().textContent = PLAY_TYPE_NAMES[item.play_type];
    row.insertCell().textContent = item.tier;
    row.insertCell().textContent = item.odds_text;
  }
}

function fillTrendMatrix(data) {
  trendMatrix.replaceChildren();
  const header = trendMatrix.insertRow();
  for (const label of ["順位", "番号組", "傾向スコア", "平均距離", "最も近い過去回"]) {
    header.appendChild(createElement("th", label));
  }
  const matchesLabel = data.lottery.startsWith("numbers") ? "桁一致" : "本数字一致";
  const distributionLength = data.sets[0]?.match_distribution.length ?? 0;
  for (let matches = 0; matches < distributionLength; matches++) {
    header.appendChild(createElement("th", matches + matchesLabel));
  }

  for (const set of data.sets) {
    const row = trendMatrix.insertRow();
    row.insertCell().textContent = String(set.rank);
    row.insertCell().textContent = set.numbers.join(" ");
    row.insertCell().textContent = set.trend_score.toFixed(2) + "/100";
    row.insertCell().textContent = set.average_distance.toFixed(4);
    row.insertCell().textContent =
      "第" + set.closest_round + "回 (" + set.closest_distance.toFixed(4) + ")";
    for (const count of set.match_distribution) {
      row.insertCell().textContent = count.toLocaleString();
    }
  }
}

function fillFrequencyMatrices(matrices) {
  frequencyMatrices.replaceChildren();
  for (const matrix of matrices) {
    const heading = createElement("h4", matrix.title);
    const wrapper = createElement("div", undefined, "table-wrap");
    const table = createElement("table", undefined, "odds");
    const header = table.insertRow();
    header.appendChild(createElement("th", "番号"));
    for (const label of matrix.labels) header.appendChild(createElement("th", label));
    const row = table.insertRow();
    row.appendChild(createElement("th", "出現回数"));
    for (const count of matrix.counts) {
      row.insertCell().textContent = count.toLocaleString();
    }
    wrapper.appendChild(table);
    frequencyMatrices.append(heading, wrapper);
  }
}

function fillCooccurrenceMatrices(matrices) {
  cooccurrenceMatrices.replaceChildren();
  for (const matrix of matrices) {
    const heading = createElement("h4", matrix.title);
    const wrapper = createElement("div", undefined, "table-wrap");
    const table = createElement("table", undefined, "odds");
    const header = table.insertRow();
    header.appendChild(createElement("th", "行 / 列"));
    for (const label of matrix.column_labels) {
      header.appendChild(createElement("th", label));
    }

    for (let rowIndex = 0; rowIndex < matrix.row_labels.length; rowIndex++) {
      const row = table.insertRow();
      row.appendChild(createElement("th", matrix.row_labels[rowIndex]));
      for (let columnIndex = 0; columnIndex < matrix.column_labels.length; columnIndex++) {
        const count = matrix.counts[rowIndex][columnIndex];
        const probability = matrix.probabilities[rowIndex][columnIndex];
        const cell = row.insertCell();
        cell.textContent = count.toLocaleString() + " (" + (probability * 100).toFixed(1) + "%)";
        cell.title =
          count.toLocaleString() + "回 / 行番号の出現 " +
          matrix.row_draw_counts[rowIndex].toLocaleString() + "回";
      }
    }
    wrapper.appendChild(table);
    cooccurrenceMatrices.append(heading, wrapper);
  }
}

// 宝くじの種類と組数の選択肢を入れる
async function loadOptions() {
  for (let count = 1; count <= MAX_SETS; count++) {
    countSelect.appendChild(createElement("option", count + "組"));
    countSelect.lastChild.value = count;
  }
  try {
    const response = await fetch("/api/lotteries");
    if (!response.ok) {
      showError(await errorMessage(response));
      return;
    }
    for (const lottery of await response.json()) {
      const option = createElement("option", lottery.name);
      option.value = lottery.value;
      lotterySelect.appendChild(option);
    }
  } catch (e) {
    showError("サーバーに接続できませんでした");
  }
}

// 「購入した」を押したら、購入の記録を API に送る
async function recordPurchase(data, set, playTypeSelect, button, message) {
  button.disabled = true;
  message.className = "purchase-message";
  try {
    const response = await fetch("/api/purchases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lottery: data.lottery,
        round: data.next_round,
        numbers: set.numbers,
        play_type: playTypeSelect.value,
      }),
    });
    if (!response.ok) {
      message.textContent = await errorMessage(response);
      message.classList.add("purchase-error");
      button.disabled = false;
      return;
    }
    const purchase = await response.json();
    message.textContent =
      "第" + purchase.round + "回・" + PLAY_TYPE_NAMES[purchase.play_type] +
      "・" + purchase.price + "円で記録しました";
    button.textContent = "記録済み";
  } catch (e) {
    message.textContent = "サーバーに接続できませんでした";
    message.classList.add("purchase-error");
    button.disabled = false;
  }
}

// 予想した番号1組の表示を作る
function createSetItem(data, set, isNumbers) {
  const item = createElement("li", undefined, "set");

  const numbers = createElement("ul", undefined, "numbers");
  for (const number of set.numbers) numbers.appendChild(createElement("li", number));
  item.appendChild(numbers);
  item.appendChild(createElement("p", set.reason, "reason"));

  // ナンバーズは組ごとに確率が変わるので、組ごとに表を出す
  if (isNumbers) {
    const table = createElement("table", undefined, "odds");
    fillOddsTable(table, set.odds, true);
    item.appendChild(table);
  }

  // 購入の記録
  const purchase = createElement("div", undefined, "purchase");
  const playTypeSelect = document.createElement("select");
  const playTypes = [...new Set(set.odds.map((odds) => odds.play_type))];
  for (const playType of playTypes) {
    const option = createElement("option", PLAY_TYPE_NAMES[playType]);
    option.value = playType;
    playTypeSelect.appendChild(option);
  }
  playTypeSelect.hidden = !isNumbers;
  const button = createElement("button", "購入した", "purchase-button");
  button.type = "button";
  const message = createElement("span", "", "purchase-message");
  button.addEventListener("click", () =>
    recordPurchase(data, set, playTypeSelect, button, message)
  );
  purchase.append(playTypeSelect, button, message);
  item.appendChild(purchase);

  return item;
}

// 予想の結果を表示する
function showResult(data) {
  const isNumbers = data.lottery.startsWith("numbers");
  resultTitle.textContent =
    data.name + " 第" + data.next_round + "回の予想（1口 " + data.price + "円）";
  resultPeriod.textContent =
    "集計期間：" + data.first_date + "〜" + data.last_date +
    "（第" + data.last_round + "回まで、" + data.total_draws + "回分）";
  trendDescription.textContent =
    "全保存期間 " + data.trend_first_date + "〜" + data.trend_last_date +
    "（" + data.trend_draw_count.toLocaleString() + "回）を " + data.trend_metric +
    " で比較した、今回の候補組どうしの過去データ類似度です。当選確率ではありません。" +
    "距離が小さい候補を上位に表示します。";
  fillTrendMatrix(data);
  fillFrequencyMatrices(data.frequency_matrices);
  fillCooccurrenceMatrices(data.cooccurrence_matrices);
  document.getElementById("history-analysis").open = false;

  // ロト系はどの組も同じ確率なので、表を1つだけ出す
  commonOddsTable.replaceChildren();
  if (!isNumbers) fillOddsTable(commonOddsTable, data.sets[0].odds, false);
  commonOdds.hidden = isNumbers;

  resultSets.replaceChildren(...data.sets.map((set) => createSetItem(data, set, isNumbers)));
  resultArea.hidden = false;
}

// 予想するボタンが押されたら API に種類と組数を送り、結果を表示する
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorArea.hidden = true;
  resultArea.hidden = true;

  predictButton.disabled = true;
  predictButton.textContent = "予想中...";
  try {
    const response = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lottery: lotterySelect.value,
        count: Number(countSelect.value),
      }),
    });
    if (!response.ok) {
      showError(await errorMessage(response));
      return;
    }
    showResult(await response.json());
  } catch (e) {
    showError("サーバーに接続できませんでした");
  } finally {
    predictButton.disabled = false;
    predictButton.textContent = "予想する";
  }
});

updateDataButton.addEventListener("click", async () => {
  updateDataButton.disabled = true;
  updateDataButton.textContent = "更新中...";
  updateDataStatus.hidden = true;
  updateDataError.hidden = true;

  try {
    const response = await fetch("/api/lottery-data/update", {
      method: "POST",
    });
    if (!response.ok) {
      updateDataError.textContent = await errorMessage(response);
      updateDataError.hidden = false;
      return;
    }

    const result = await response.json();
    updateDataStatus.textContent = "公式サイトを確認しました（当せん番号 " +
      result.added_draws + " 件、賞金 " + result.added_prizes + " 件を更新）。";
    updateDataStatus.hidden = false;
  } catch (e) {
    updateDataError.textContent = "サーバーに接続できませんでした";
    updateDataError.hidden = false;
  } finally {
    updateDataButton.disabled = false;
    updateDataButton.textContent = "最新情報を更新";
  }
});

loadOptions();

// ---- タブの切り替え ----

const tabs = document.querySelectorAll(".tab");
const tabPanels = document.querySelectorAll(".tab-panel");

// 押されたタブの中身だけを表示する
for (const tab of tabs) {
  tab.addEventListener("click", () => {
    for (const other of tabs) other.classList.toggle("active", other === tab);
    for (const panel of tabPanels) panel.hidden = panel.id !== tab.dataset.tab;
    if (tab.dataset.tab === "purchases-tab") loadPurchases("GET", "/api/purchases");
  });
}

// ---- 収支タブ ----

const checkButton = document.getElementById("check-button");
const checkStatus = document.getElementById("check-status");
const purchasesError = document.getElementById("purchases-error");
const purchasesTable = document.getElementById("purchases-table");
const purchasesEmpty = document.getElementById("purchases-empty");
const summaryNote = document.getElementById("summary-note");

// 結果の状態の表示名
const STATUS_NAMES = {
  pending: "未確認",
  won: "当せん",
  lost: "外れ",
  prize_unknown: "賞金未登録",
};

// 金額を「1,234円」の形にする
function yen(amount) {
  return Math.round(amount).toLocaleString("ja-JP") + "円";
}

// 全体の収支を表示する
function showSummary(summary) {
  document.getElementById("summary-spent").textContent = yen(summary.spent);
  document.getElementById("summary-won").textContent = yen(summary.won);
  const profit = document.getElementById("summary-profit");
  profit.textContent = (summary.profit > 0 ? "+" : "") + yen(summary.profit);
  profit.className = summary.profit < 0 ? "minus" : "plus";
  document.getElementById("summary-expected").textContent = yen(summary.expected_return);

  const notes = [];
  if (summary.pending_count > 0) notes.push("結果がまだの購入が " + summary.pending_count + " 件あります。");
  if (summary.expected_is_partial) notes.push("賞金のデータがない購入は、期待される戻りに含めていません。");
  notes.push("期待される戻り：当せん確率 × これまでの平均の賞金。長く買い続けたときの平均の目安です。");
  summaryNote.textContent = notes.join(" ");
}

// 購入の一覧の表を作る
function showPurchases(purchases) {
  purchasesTable.replaceChildren();
  purchasesEmpty.hidden = purchases.length > 0;
  if (purchases.length === 0) return;

  const header = purchasesTable.insertRow();
  for (const title of [
    "種類", "回", "購入番号", "当せん番号", "ボーナス番号",
    "申込タイプ", "金額", "結果", "賞金", "購入日時",
  ]) {
    header.appendChild(createElement("th", title));
  }
  for (const purchase of purchases) {
    const row = purchasesTable.insertRow();
    row.insertCell().textContent = purchase.name;
    row.insertCell().textContent = "第" + purchase.round + "回";
    row.insertCell().textContent = purchase.numbers.join(", ");
    row.insertCell().textContent = purchase.winning_numbers === null
      ? "-"
      : purchase.winning_numbers.join(", ");
    row.insertCell().textContent = purchase.bonus_numbers === null
      ? "-"
      : (purchase.bonus_numbers.length === 0 ? "なし" : purchase.bonus_numbers.join(", "));
    row.insertCell().textContent = PLAY_TYPE_NAMES[purchase.play_type];
    row.insertCell().textContent = yen(purchase.price);
    const status = row.insertCell();
    status.textContent = STATUS_NAMES[purchase.status] + (purchase.tier ? "（" + purchase.tier + "）" : "");
    status.className = "status-" + purchase.status;
    row.insertCell().textContent = purchase.prize === null ? "-" : yen(purchase.prize);
    row.insertCell().textContent = purchase.purchased_at.replace("T", " ");
  }
}

// 購入の一覧と収支を API から取得して表示する（POST のときは結果の確認もする）
async function loadPurchases(method, url) {
  purchasesError.hidden = true;
  try {
    const response = await fetch(url, { method });
    if (!response.ok) {
      purchasesError.textContent = await errorMessage(response);
      purchasesError.hidden = false;
      return null;
    }
    const data = await response.json();
    showSummary(data.summary);
    showPurchases(data.purchases);
    return data;
  } catch (e) {
    purchasesError.textContent = "サーバーに接続できませんでした";
    purchasesError.hidden = false;
    return null;
  }
}

// 「結果を確認」が押されたら、照らし合わせて一覧を更新する
checkButton.addEventListener("click", async () => {
  checkButton.disabled = true;
  checkButton.textContent = "確認中...";
  checkStatus.hidden = true;
  const result = await loadPurchases("POST", "/api/purchases/check");
  if (result) {
    checkStatus.textContent = result.checked_count === 0
      ? "確認しました。新しく確認できる抽せん結果はありません。"
      : result.checked_count + " 件の購入結果を新しく確認しました。";
    checkStatus.hidden = false;
  }
  checkButton.disabled = false;
  checkButton.textContent = "結果を確認";
});

// ---- 相談タブ ----

const agentForm = document.getElementById("agent-form");
const agentMessage = document.getElementById("agent-message");
const agentButton = document.getElementById("agent-button");
const agentReset = document.getElementById("agent-reset");
const agentLog = document.getElementById("agent-log");
const agentError = document.getElementById("agent-error");

// 会話を見分ける番号（ページを開き直すか「新しい会話」で変わる）
let threadId = crypto.randomUUID();

// 会話の1発言を表示する
function addAgentMessage(role, text) {
  const item = createElement("li", text, "agent-message agent-" + role);
  agentLog.appendChild(item);
  item.scrollIntoView({ block: "nearest" });
}

// 送信が押されたら、エージェントに質問して返答を表示する
agentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  agentError.hidden = true;
  const message = agentMessage.value;
  if (!message.trim()) {
    agentError.textContent = "質問を入力してください";
    agentError.hidden = false;
    return;
  }

  addAgentMessage("user", message);
  agentMessage.value = "";
  agentButton.disabled = true;
  agentButton.textContent = "考え中...";
  try {
    const response = await fetch("/api/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: threadId }),
    });
    if (!response.ok) {
      agentError.textContent = await errorMessage(response);
      agentError.hidden = false;
      return;
    }
    addAgentMessage("assistant", (await response.json()).answer);
  } catch (e) {
    agentError.textContent = "サーバーに接続できませんでした";
    agentError.hidden = false;
  } finally {
    agentButton.disabled = false;
    agentButton.textContent = "送信";
  }
});

// 「新しい会話」が押されたら、会話の記憶と表示を消す
agentReset.addEventListener("click", () => {
  threadId = crypto.randomUUID();
  agentLog.replaceChildren();
  agentError.hidden = true;
});
