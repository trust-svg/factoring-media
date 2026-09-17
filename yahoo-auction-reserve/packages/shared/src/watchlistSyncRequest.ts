// 画面の「今すぐ更新」を受け付けてよいかの判定。
//
// なぜ判定が要るか:
//   ウォッチリスト同期は1回ごとに Chromium を起動し、ログイン済みの状態で
//   ヤフオクを開く。このアプリで一番避けたいのは **必要のないヤフオク
//   アクセス**(bot 検知)なので、連打・複数タブ・リロードがそのまま
//   同期回数にならないようにする。
//
// ⚠️ 「前回の同期からの経過時間」だけで測ってはいけない。同期は Chromium の
//    起動と商品ごとの取得で数十秒〜数分かかり、その間 lastWatchlistSyncAt は
//    **古いまま**なので、走っている最中は何回でも通ってしまう。
//    要求時刻(watchlistSyncRequestedAt)と合わせて新しいほうで測る。

/** 手動同期を受け付ける最短間隔 */
export const MANUAL_WATCHLIST_SYNC_MIN_INTERVAL_MS = 3 * 60 * 1000;

export interface ManualSyncSessionState {
  /** 同期が最後に成功した時刻 */
  lastWatchlistSyncAt: Date | null;
  /** 手動同期の要求が立っている時刻(worker が実行し終えると null に戻る) */
  watchlistSyncRequestedAt: Date | null;
}

export type ManualSyncVerdict =
  /** 要求を立ててよい */
  | { kind: "ACCEPT" }
  /** すでに要求済み。立て直さずに待たせる */
  | { kind: "PENDING" }
  /** 直前に同期したばかり */
  | { kind: "TOO_SOON"; retryAfterSec: number }
  /** そもそも連携が無い */
  | { kind: "NO_SESSION" };

export function judgeManualWatchlistSync(
  sessions: ManualSyncSessionState[],
  nowMs: number,
  minIntervalMs: number = MANUAL_WATCHLIST_SYNC_MIN_INTERVAL_MS,
): ManualSyncVerdict {
  if (sessions.length === 0) return { kind: "NO_SESSION" };

  // 要求が残っているうちは何度押されても1回ぶんにまとめる。
  // 押した側から見れば「受け付けた」と同じなので、待ちの表示にそのまま繋ぐ
  if (sessions.some((s) => s.watchlistSyncRequestedAt !== null)) {
    return { kind: "PENDING" };
  }

  const lastSyncedMs = sessions.reduce(
    (max, s) => Math.max(max, s.lastWatchlistSyncAt?.getTime() ?? Number.NEGATIVE_INFINITY),
    Number.NEGATIVE_INFINITY,
  );
  // 一度も同期できていない連携しか無いなら、待たせる理由が無い
  if (!Number.isFinite(lastSyncedMs)) return { kind: "ACCEPT" };

  const elapsed = nowMs - lastSyncedMs;
  if (elapsed < minIntervalMs) {
    // ⚠️ 上限を間隔そのものに丸める。時計のずれで未来の同期時刻が入ると
    //    「あと9999秒待て」という現実離れした案内になる
    const waitMs = Math.min(minIntervalMs, minIntervalMs - elapsed);
    return { kind: "TOO_SOON", retryAfterSec: Math.max(1, Math.ceil(waitMs / 1000)) };
  }
  return { kind: "ACCEPT" };
}
