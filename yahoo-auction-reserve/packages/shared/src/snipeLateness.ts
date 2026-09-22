/**
 * スナイプが「予定より遅れて実行された」ときに、それが**故障なのか算数なのか**を分ける。
 *
 * 背景(2026-09-20 実測): 自動延長のあとの再スナイプでは、ほぼ必ず
 * 「予定より41秒遅れて実行(monitor の起動遅れ)」が出ていた。しかし worker は
 * 止まっておらず Redis も詰まっていない。ヤフオクの自動延長は終了を **5分(300秒)**
 * しか伸ばさないので、延長を検知した瞬間の新しい終了時刻は今から約300秒後しかない。
 * そこへ `snipeAt = endAt - snipeSecondsBefore` を当てると、
 *
 *     snipeSecondsBefore = 330 → snipeAt = (今 + 300) - 330 = 今 - 30 秒(生まれた瞬間すでに過去)
 *
 * となり、`sleepUntil` は過去時刻で即座に返る。そこにループ自身の仕事
 * (価格取得・DB更新・通知)の十数秒が乗って 41秒。**snipeSecondsBefore が
 * 延長幅より大きい予約は、延長が起きるたび必ずこの警告を出す。**
 *
 * 入札そのものは害を受けない(「遅れる」＝終了に近づく方向なので、スナイプとしては
 * むしろ有利)。害は**警報が意味を失うこと**で、本物の worker 停止が来ても同じ文面に
 * 埋もれる([[gotcha_alert_note_pre_labels_the_red_as_expected]] と同型)。
 *
 * ⚠️ 直し方として `SNIPE_LATE_TOLERANCE_SECONDS` を緩めるのは誤り。閾値をいくつに
 * しても「避けられない遅れ」と「起動遅れ」を区別できないままで、本物を見逃す幅が
 * 広がるだけ。ここでは遅れを**測った3つの量に分解**して、残りだけを警告する。
 *
 *   1. unavoidableSec — snipeAt を算出した時点で既に過去だった分。取り返す手段が無い
 *   2. loopWorkSec    — その算出から待機に入るまでにループが実際に使った時間
 *                       (価格取得・DB更新・通知)。待ち時間に余裕がある回は
 *                       待機の中に吸収されて 0 秒の遅れになるが、1 が正なら
 *                       そのまま遅れとして積み上がる。**これも故障ではない**
 *   3. 残り           — 1 でも 2 でも説明できない分。ここだけが monitor の疑い
 *
 * どれもハードコードでなく実測なので、ヤフオクが延長幅を変えても壊れない。
 * ただし 2 が青天井だと「fetchAuctionInfo が5分ハングした」まで正常扱いになるため、
 * ウォームアップ予算(`MONITOR_WARMUP_SECONDS`)を超えたループ仕事は故障として扱う。
 */
import { MONITOR_WARMUP_SECONDS, SNIPE_LATE_TOLERANCE_SECONDS } from "./constants";

export type SnipeLatenessLevel =
  /** 予定どおり(許容範囲内) */
  | "ON_TIME"
  /** 遅れているが、その全部が算出時点で確定していた不可避分 = 故障ではない */
  | "STRUCTURAL"
  /** 不可避分を差し引いてもなお遅れている = monitor 側を疑う */
  | "DELAYED";

export interface SnipeLateness {
  level: SnipeLatenessLevel;
  /** 予定時刻からの総遅れ(秒)。早ければ 0 */
  lateBySec: number;
  /** そのうち構造的に避けられなかった分(秒) */
  unavoidableSec: number;
  /** ループ自身の仕事に使った分(秒) */
  loopWorkSec: number;
  /** 1 でも 2 でも説明できない遅れ(秒)。ここが閾値を超えたときだけ警告する */
  excessSec: number;
  /** ログと BidAttempt.detail に残す1行。ON_TIME なら null */
  note: string | null;
}

export function classifySnipeLateness(input: {
  /** yahooNow() - snipeAt (秒) */
  lateBySec: number;
  /** snipeAt を算出した時点で既に過去だった秒数(0 以上) */
  unavoidableSec: number;
  /** snipeAt の算出から待機に入るまでにループが使った秒数(0 以上) */
  loopWorkSec: number;
  toleranceSec?: number;
}): SnipeLateness {
  const tolerance = input.toleranceSec ?? SNIPE_LATE_TOLERANCE_SECONDS;
  // 早く起きた場合は 0 に丸める。「-2秒遅れ」は読み手を混乱させるだけで、
  // 早いこと自体は問題にならない(sleepUntil が待つ)。
  const lateBySec = Math.max(0, input.lateBySec);
  const unavoidableSec = Math.min(Math.max(0, input.unavoidableSec), lateBySec);
  // ⚠️ ループ仕事を差し引いてよいのは**不可避分がある回だけ**。待つ余裕が
  // あった回(unavoidableSec = 0)にループ仕事が遅れとして現れたなら、それは
  // 待機に吸収されなかった＝予定を食い潰したということで、故障の側に置く。
  const creditedLoopWork =
    unavoidableSec > 0 ? Math.min(Math.max(0, input.loopWorkSec), lateBySec - unavoidableSec) : 0;
  const loopWorkSec = Math.max(0, input.loopWorkSec);
  const excessSec = lateBySec - unavoidableSec - creditedLoopWork;
  const parts = [
    `不可避分${unavoidableSec}秒`,
    `ループ処理${creditedLoopWork}秒`,
    `説明不能${excessSec}秒`,
  ].join(" + ");

  // ループ仕事が青天井だと、fetchAuctionInfo のハングまで正常扱いになる。
  // ウォームアップに積んである予算を超えたら、内訳に関係なく故障として扱う。
  const loopWorkTooSlow = loopWorkSec > MONITOR_WARMUP_SECONDS;
  if (excessSec > tolerance || loopWorkTooSlow) {
    // ⚠️ 不可避分があるときは必ず内訳を書く。書かないと、次に読む人が
    // また「41秒も遅れている」と読んで存在しない故障を探しに行く。
    const breakdown =
      unavoidableSec > 0 || loopWorkTooSlow
        ? `(${parts}${loopWorkTooSlow ? " / ループ処理が異常に長い" : ""})`
        : "(monitor の起動遅れ)";
    return {
      level: "DELAYED",
      lateBySec,
      unavoidableSec,
      loopWorkSec,
      excessSec,
      note: `予定より${lateBySec}秒遅れて実行${breakdown}`,
    };
  }
  if (lateBySec > tolerance) {
    return {
      level: "STRUCTURAL",
      lateBySec,
      unavoidableSec,
      loopWorkSec,
      excessSec,
      note:
        `予定時刻が算出時点で既に${unavoidableSec}秒過去だったため即時実行` +
        `(合計${lateBySec}秒 = ${parts}。実行秒数が自動延長の延長幅より長いときに起きる正常動作)`,
    };
  }
  return { level: "ON_TIME", lateBySec, unavoidableSec, loopWorkSec, excessSec, note: null };
}
