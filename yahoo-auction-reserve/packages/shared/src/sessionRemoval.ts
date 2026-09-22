// =============================================================
// 連携解除の進め方を決める
//
// なぜ要るか(2026-09-22 に実際に起きたこと):
//   設計 §8 は「連携解除は物理削除」だったが、BidReservation と
//   WatchlistItem の外部キーはどちらも RESTRICT。一度でも使った連携は
//   **DB が削除を拒否する**。失効した連携を画面から消そうとすると
//   P2003 で 500 になり、画面には「サーバーエラーが発生しました」しか
//   出ないので、消えない理由が誰にも分からなかった
//   (実測: 予約17件 + ウォッチ101件がぶら下がっていた)。
//
// ⚠️ 落札履歴(WON)は消してはいけない。古物台帳の対象になる取引記録で、
//   カスケード削除にすると取り返しがつかない。
//
// だから解除は2通りある:
//   - 一度も使っていない連携 → 物理削除(貼り間違いの痕跡を残さない)
//   - 使った連携 → **無害化**。Cookie を捨てて REVOKED にし、履歴は残す
// どちらでも「認証情報が消える」という解除の主目的は果たす。
// =============================================================

export type SessionRemovalPlan =
  | { mode: "delete" }
  | { mode: "revoke"; reason: string };

export interface SessionDependencies {
  /** この連携にひもづく予約の件数(status を問わない) */
  reservations: number;
  /** この連携が取り込んだウォッチ商品の件数 */
  watchlistItems: number;
}

export function planSessionRemoval(deps: SessionDependencies): SessionRemovalPlan {
  const left: string[] = [];
  if (deps.reservations > 0) left.push(`予約 ${deps.reservations}件`);
  if (deps.watchlistItems > 0) left.push(`ウォッチ商品 ${deps.watchlistItems}件`);

  if (left.length === 0) return { mode: "delete" };

  // ⚠️ 件数を必ず書く。「消せませんでした」だけだと、何が残っているのか
  //    分からず、また同じところで詰まる(今回がまさにそれ)。
  return {
    mode: "revoke",
    reason: `${left.join("と")}が残っているため、記録は残したまま解除しました`,
  };
}
