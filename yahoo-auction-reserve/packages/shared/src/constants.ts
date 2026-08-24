// スナイプ実行タイミング(設計 §7.1 / 競合分析 S-2)
export const SNIPE_SECONDS_DEFAULT = 30;
export const SNIPE_SECONDS_MIN = 5;
export const SNIPE_SECONDS_MAX = 600;

// monitor-job のウォームアップに要する時間(ブラウザ起動 → Cookie 注入 →
// 商品ページ読み込み → ログイン判定)。実測が取れたらこの値を更新する。
export const MONITOR_WARMUP_SECONDS = 60;

/**
 * monitor-job を起動する時刻(終了何秒前か)。
 *
 * ⚠️ **固定値にしてはいけない**。
 * 以前ここは `MONITOR_LEAD_SECONDS = 90` の固定値だった。
 * snipeSecondsBefore が 90 を超えると、monitor は T-90 に起きた時点で
 * 「T-(snipe秒) まで待つ」の目標時刻を既に過ぎており、sleepUntil が即座に
 * 返って **設定と無関係に T-90 で入札していた**。エラーも警告も出ないので、
 * 「300秒前に入札したはずが実際は90秒前」という形でしか表面化しない。
 * 上限を 600 秒に上げたことで最大 510 秒ズレる状態だった。
 */
export function monitorLeadSeconds(snipeSecondsBefore: number): number {
  return snipeSecondsBefore + MONITOR_WARMUP_SECONDS;
}

/**
 * 予約の登録・変更を締め切る時刻(終了何秒前か)。
 *
 * monitor-job が起動してしまうと、その中で読んだ予約内容で最後まで走るので、
 * 後から金額や実行秒数を変えても反映されない。締切は必ず monitor の起動より
 * 前に置く(= snipe秒 + ウォームアップ + 余裕)。
 */
export const EDIT_DEADLINE_MARGIN_SECONDS = 60;
export function editDeadlineSeconds(snipeSecondsBefore: number): number {
  return monitorLeadSeconds(snipeSecondsBefore) + EDIT_DEADLINE_MARGIN_SECONDS;
}

/**
 * 予定時刻からこの秒数以上遅れて入札した場合は「遅延入札」として記録する。
 * (worker 停止・Redis 詰まりなどで monitor の起動自体が遅れたケース)
 */
export const SNIPE_LATE_TOLERANCE_SECONDS = 3;

// refresh-job のポーリング間隔
export const REFRESH_INTERVAL_FAR_MS = 30 * 60 * 1000; // 終了15分前まで
export const REFRESH_INTERVAL_NEAR_MS = 5 * 60 * 1000; // 終了15分前以降

// 自動延長の再スナイプループ上限(設計 §7.2)
export const EXTENSION_LOOP_MAX_COUNT = 20;
export const EXTENSION_LOOP_MAX_MS = 30 * 60 * 1000;

// ヤフオクセッションの有効性チェック間隔
export const SESSION_VERIFY_INTERVAL_MS = 6 * 60 * 60 * 1000;

export const YAHOO_AUCTION_URL_PATTERN =
  /^https:\/\/(?:page\.auctions\.yahoo\.co\.jp\/jp\/auction\/|auctions\.yahoo\.co\.jp\/jp\/auction\/)([A-Za-z0-9]+)/;
