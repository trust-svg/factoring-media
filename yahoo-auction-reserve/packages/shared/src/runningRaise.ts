import { minimumBidToBeat } from "./bidUnit";

/**
 * 走行中(監視中・入札中)の予約に対する「上限額の引き上げ」の検証。
 *
 * 入札後に高値更新されたとき、同じ予約のまま増額して入札しなおすための唯一の
 * 手動経路。monitor がスナイプ時刻の直前に予約を読み直すので、ここで DB に
 * 書けば走っているジョブが拾う。
 *
 * ⚠️ 引き上げ **以外** は受けない。すでに送った入札は取り消せないので上限を
 * 下げても意味が無く、実行タイミングやテスト実行を今さら変えると、走っている
 * ループが起動時に持った前提と食い違ったまま入札が飛ぶ。
 */
export interface RunningRaiseTarget {
  maxBidAmount: number;
  currentPrice: number | null;
  endAt: Date;
}

export type RunningRaiseResult =
  | { ok: true; maxBidAmount: number }
  | { ok: false; status: 400 | 409; error: string };

export function validateRunningRaise(
  body: Record<string, unknown>,
  reservation: RunningRaiseTarget,
  nowMs: number,
): RunningRaiseResult {
  // ⚠️ 「maxBidAmount が入っているか」ではなく「maxBidAmount **だけ** か」で見る。
  // 前者だと、UI が他の項目も一緒に送ってきたときに黙って無視することになり、
  // 「変更したのに反映されない」が起きる。混ざっていたら断る。
  const keys = Object.keys(body).filter((k) => body[k] !== undefined);
  if (keys.length !== 1 || keys[0] !== "maxBidAmount") {
    return { ok: false, status: 409, error: "実行中に変更できるのは上限額の引き上げだけです" };
  }
  const v = Number(body.maxBidAmount);
  if (!Number.isInteger(v) || v <= reservation.maxBidAmount) {
    return {
      ok: false,
      status: 400,
      error: `上限額は現在の ¥${reservation.maxBidAmount} より高い整数で指定してください`,
    };
  }
  // ⚠️ 現在価格そのものではなく、**上回るのに必要な額** と比べる。ヤフオクは
  // 入札単位刻みでしか受け付けないので、現在価格 +1 円のような増額は通しても
  // 入札できず、「増額したのに負けた」だけが起きる。
  if (reservation.currentPrice !== null) {
    const required = minimumBidToBeat(reservation.currentPrice);
    if (v < required) {
      return {
        ok: false,
        status: 400,
        error: `現在価格 ¥${reservation.currentPrice} を上回るには ¥${required} 以上が必要です`,
      };
    }
  }
  if (reservation.endAt.getTime() <= nowMs) {
    return { ok: false, status: 409, error: "オークションが終了しているため変更できません" };
  }
  return { ok: true, maxBidAmount: v };
}
