// スナイプ実行タイミング(設計 §7.1 / 競合分析 S-2)
export const SNIPE_SECONDS_DEFAULT = 30;
export const SNIPE_SECONDS_MIN = 5;
export const SNIPE_SECONDS_MAX = 300;

// monitor-job をブラウザウォームアップのため起動する時刻(終了何秒前)
export const MONITOR_LEAD_SECONDS = 90;

// 予約の登録・変更を締め切る時刻(終了何秒前)
export const EDIT_DEADLINE_SECONDS = 60;

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
