// Run this in DevTools Console on a Mizuho lottery results page.
// The official site serves one Shift_JIS CSV per draw.
(async () => {
  const origin = "https://www.mizuhobank.co.jp";
  if (location.origin !== origin) {
    throw new Error("Open a Mizuho Bank lottery results page before running this script.");
  }

  const cutoff = "2011-10-31";
  const games = [
    { family: "numbers", prefix: "100", firstKnownRound: 3000, latestKnownRound: 7104 },
    { family: "miniloto", prefix: "101", firstKnownRound: 1, latestKnownRound: 1410 },
    { family: "loto6", prefix: "102", firstKnownRound: 1, latestKnownRound: 2150 },
    { family: "loto7", prefix: "103", firstKnownRound: 1, latestKnownRound: 701 },
  ];
  const concurrency = 5;
  const pauseBetweenBatchesMs = 1000;
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function drawDate(csvText) {
    const header = csvText.split(/\r?\n/)[1];
    const dateText = header?.split(",")[2] ?? "";
    const match = dateText.match(/^(令和|平成|昭和)(\d+)年(\d+)月(\d+)日$/);
    if (!match) {
      throw new Error(`Could not read the draw date: ${dateText || "(missing)"}`);
    }
    const eraBase = { 令和: 2018, 平成: 1988, 昭和: 1925 }[match[1]];
    const year = eraBase + Number(match[2]);
    return `${year}-${String(match[3]).padStart(2, "0")}-${String(match[4]).padStart(2, "0")}`;
  }

  async function fetchRound(game, round, allowMissing = false) {
    const filename = `A${game.prefix}${String(round).padStart(4, "0")}.CSV`;
    const url = `${origin}/retail/takarakuji/${game.family === "numbers" ? "numbers" : `loto/${game.family}`}/csv/${filename}`;
    const response = await fetch(url, { credentials: "same-origin" });
    if (allowMissing && response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error(`${filename}: HTTP ${response.status}`);
    }
    const bytes = await response.arrayBuffer();
    const text = new TextDecoder("shift_jis").decode(bytes);
    const roundMatch = text.split(/\r?\n/)[1]?.match(/^第\s*0*(\d+)\s*回/);
    if (!roundMatch || Number(roundMatch[1]) !== round) {
      throw new Error(`${filename}: CSV draw number does not match the requested round`);
    }
    const actualDate = drawDate(text);
    return { round, text, draw_date: actualDate };
  }

  async function findLatestRound(game) {
    let low = game.latestKnownRound;
    let high = low * 2;
    while (await fetchRound(game, high, true)) {
      low = high;
      high *= 2;
    }

    while (low + 1 < high) {
      const middle = Math.floor((low + high) / 2);
      if (await fetchRound(game, middle, true)) {
        low = middle;
      } else {
        high = middle;
      }
    }
    return low;
  }

  if (!confirm(
    "This will read several thousand public, per-draw CSV files from Mizuho Bank " +
    "using the browser, in small batches. It can take several minutes. Continue?"
  )) {
    return;
  }

  const collected = [];
  for (const game of games) {
    const latestRound = await findLatestRound(game);
    const firstKnown = await fetchRound(game, game.firstKnownRound);
    let low = game.firstKnownRound;
    let high = latestRound;

    while (firstKnown.draw_date < cutoff && low < high) {
      const middle = Math.floor((low + high) / 2);
      const record = await fetchRound(game, middle);
      if (record.draw_date < cutoff) {
        low = middle + 1;
      } else {
        high = middle;
      }
    }

    const firstRound = low;
    console.info(
      `${game.family}: rounds ${firstRound}-${latestRound} ` +
      `(${firstKnown.draw_date} baseline; latest CSV detected)`
    );
    for (let start = firstRound; start <= latestRound; start += concurrency) {
      const end = Math.min(start + concurrency, latestRound + 1);
      const batch = await Promise.all(
        Array.from({ length: end - start }, (_, offset) => fetchRound(game, start + offset))
      );
      collected.push(...batch.map((record) => ({
        family: game.family,
        round: record.round,
        text: record.text,
      })));
      console.info(`${game.family}: collected through round ${end - 1}`);
      await delay(pauseBetweenBatchesMs);
    }
  }

  const payload = {
    source: "Mizuho Bank official per-draw CSVs",
    cutoff,
    collected_at: new Date().toISOString(),
    files: collected,
  };
  const blob = new Blob([JSON.stringify(payload)], { type: "application/json;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "mizuho_lottery_history.json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
  console.info(`Finished: ${collected.length} CSV files. Download mizuho_lottery_history.json.`);
})();
