// 画面表示用の純粋関数。DB もネットワークも触らないので、そのままテストできる。
// (クライアントコンポーネントからも使うため node:crypto を持ち込まないこと)

export const JST_OFFSET_MS = 9 * 60 * 60 * 1000;

/**
 * JST での「その日」を表すキー(YYYY-MM-DD)。
 *
 * ⚠️ `toLocaleDateString("ja-JP", { timeZone: "Asia/Tokyo" })` を使わないのは、
 * 実行環境の ICU データ有無で結果が変わるため(小さい Docker イメージでは
 * timeZone 指定が黙って無視され、UTC の日付が返る)。
 * オフセットを足してから UTC 系のゲッタで読む形にして環境非依存にする。
 */
export function jstDayKey(d: Date): string {
  const shifted = new Date(d.getTime() + JST_OFFSET_MS);
  const y = shifted.getUTCFullYear();
  const m = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  const day = String(shifted.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function isSameJstDay(a: Date, b: Date): boolean {
  return jstDayKey(a) === jstDayKey(b);
}

/** JST での月/日(曜)。見出し用。 */
export function formatJstDayLabel(d: Date): string {
  const shifted = new Date(d.getTime() + JST_OFFSET_MS);
  const wd = ["日", "月", "火", "水", "木", "金", "土"][shifted.getUTCDay()];
  return `${shifted.getUTCMonth() + 1}/${shifted.getUTCDate()}(${wd})`;
}

/** JST の HH:MM:SS。 */
export function formatJstTime(d: Date, withSeconds = true): string {
  const shifted = new Date(d.getTime() + JST_OFFSET_MS);
  const hh = String(shifted.getUTCHours()).padStart(2, "0");
  const mm = String(shifted.getUTCMinutes()).padStart(2, "0");
  if (!withSeconds) return `${hh}:${mm}`;
  return `${hh}:${mm}:${String(shifted.getUTCSeconds()).padStart(2, "0")}`;
}

/**
 * 残り時間の表示。桁位置が行をまたいで揃うよう、区切りは常にコロン。
 * - 24時間以上: `3日 04:12`
 * - 1時間以上:  `02:31:07`
 * - 1時間未満:  `08:47`
 */
export function formatRemaining(ms: number): string {
  if (ms <= 0) return "終了";
  const total = Math.floor(ms / 1000);
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const p = (n: number) => String(n).padStart(2, "0");
  if (d > 0) return `${d}日 ${p(h)}:${p(m)}`;
  if (h > 0) return `${p(h)}:${p(m)}:${p(s)}`;
  return `${p(m)}:${p(s)}`;
}

export type Urgency = "NORMAL" | "TODAY" | "URGENT";

/** 残り10分以内で URGENT。今日終了なら TODAY。 */
export const URGENT_THRESHOLD_MS = 10 * 60 * 1000;

export function urgencyOf(endAt: Date, now: Date): Urgency {
  const left = endAt.getTime() - now.getTime();
  if (left <= URGENT_THRESHOLD_MS) return "URGENT";
  return isSameJstDay(endAt, now) ? "TODAY" : "NORMAL";
}

/** 現在価格が上限のこの割合を超えたら、上限額を警告色にする。 */
export const CAP_NEAR_RATIO = 0.8;

export function isNearCap(currentPrice: number | null | undefined, cap: number): boolean {
  if (currentPrice == null || cap <= 0) return false;
  return currentPrice / cap >= CAP_NEAR_RATIO;
}

export function formatYen(n: number): string {
  return `¥${n.toLocaleString("ja-JP")}`;
}
