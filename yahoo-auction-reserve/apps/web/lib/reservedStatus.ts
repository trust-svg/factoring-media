import { isRebookableReservation } from "@yar/shared/labels";

/**
 * 商品ID → 予約の状態を「動いている予約」と「予約し直せる過去の予約」に分ける。
 *
 * ⚠️ ウォッチリスト画面が `予約が1件でもあれば予約済み` と読んでいたせいで、
 * キャンセルした商品の行から操作(予約する / 一覧から消す)が全部消え、
 * **ウォッチリストからは二度と予約できなくなっていた**(2026-09-02 報告)。
 * 予約API は最初から再登録を許していたので、壊れていたのは画面だけ。
 *
 * ページ(サーバコンポーネント)に直接書くと prisma を引きずってテストできない。
 * 判断だけをここに出して、素の値で確かめられる形にしておく。
 */
export function splitReservedStatuses(
  reservations: { auctionId: string; status: string }[],
): { live: Map<string, string>; past: Map<string, string> } {
  const live = new Map<string, string>();
  const past = new Map<string, string>();
  for (const r of reservations) {
    if (isRebookableReservation(r.status)) past.set(r.auctionId, r.status);
    else live.set(r.auctionId, r.status);
  }
  return { live, past };
}
