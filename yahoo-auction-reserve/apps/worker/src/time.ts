// サーバ時刻とヤフオク側時刻のオフセット補正(設計 §4)
// ヤフオクトップへの HEAD リクエストの Date ヘッダから概算オフセットを測る。
// Date ヘッダは秒精度なので ±1s 程度の誤差は残る前提で扱うこと。

let offsetMs = 0;
let lastMeasuredAt = 0;

export async function measureYahooTimeOffset(): Promise<number> {
  try {
    const before = Date.now();
    const res = await fetch("https://auctions.yahoo.co.jp/", {
      method: "HEAD",
      redirect: "follow",
    });
    const after = Date.now();
    const dateHeader = res.headers.get("date");
    if (dateHeader) {
      const serverTime = new Date(dateHeader).getTime();
      const rtt = after - before;
      // サーバ時刻はレスポンス生成時点 ≒ before + rtt/2 に対応するとみなす
      offsetMs = serverTime - (before + rtt / 2);
      lastMeasuredAt = Date.now();
    }
  } catch (err) {
    console.warn("[time] offset measurement failed:", err);
  }
  return offsetMs;
}

export function yahooNow(): Date {
  return new Date(Date.now() + offsetMs);
}

export function offsetIsStale(): boolean {
  return Date.now() - lastMeasuredAt > 10 * 60 * 1000;
}

export async function sleepUntil(target: Date): Promise<void> {
  // 長い待機は粗いsleepで消化し、直前は短い間隔で詰める
  for (;;) {
    const remaining = target.getTime() - yahooNow().getTime();
    if (remaining <= 0) return;
    await sleep(remaining > 2000 ? remaining - 1500 : Math.min(remaining, 25));
  }
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
