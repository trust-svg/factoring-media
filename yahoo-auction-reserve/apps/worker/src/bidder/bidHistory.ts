import { extractAuctionId } from "@yar/shared";

export type ResultVerdict = "WON" | "LOST" | "UNKNOWN";

/**
 * 落札できたかどうかは **入札履歴ページでしか分からない**。
 *
 * ⚠️ 2026-08-29 実測(n1242036522・こちらが11円で最高額入札者だった商品)。
 * 終了後の商品ページに載っていた状態表示は
 * **「このオークションは終了しています」の1行だけ**で、
 * 落札者名も「あなたが落札しました」も「高値更新」も **存在しなかった**。
 * つまり商品ページを読む限り WON と LOST は永久に区別できない
 * (旧 checkResult は必ず UNKNOWN を返していた)。
 *
 * 同じ商品の入札履歴ページ(/jp/show/bid_hist?aID=...)には両方あった:
 *
 *   ymb******** / 評価：238 最高額入札者   21 円  1  8月 29日 21時 32分
 *   Royal Coin Japan / 評価：186（評価の詳細） 11 円  1  8月 29日 0時 40分
 *
 * ここが要点で、**自分の行だけ ID が伏字にならない**。他人は `ymb********` の
 * ように伏せられるが、自分は表示名がそのまま出る。その表示名はヘッダの
 * loggedInIndicator(`a.mhdPcUserName__link`)と同じ文字列なので、
 * 「自分の行を特定し、その行に『最高額入札者』が付いているか」で勝敗が決まる。
 * この1ページに WON 側(ymb の行)と LOST 側(自分の行)の陽性対照が両方あった。
 */
export const HIGHEST_BIDDER_MARK = "最高額入札者";

/** 入札者の行だけが持つ列見出し。ヘッダ行や案内文を弾くために使う */
const BIDDER_ROW_MARK = "評価";

export function bidHistoryUrl(auctionUrl: string): string | null {
  const id = extractAuctionId(auctionUrl);
  return id ? `https://auctions.yahoo.co.jp/jp/show/bid_hist?aID=${id}` : null;
}

export interface BidHistoryInput {
  /** 入札履歴ページの各行(`tr`)のテキスト */
  rows: string[];
  /** ヘッダに出ている自分の表示名(loggedInIndicator の実テキスト) */
  myDisplayName: string;
}

/**
 * 入札履歴の行から勝敗を決める。
 *
 * ⚠️ 分からないときは必ず UNKNOWN を返す。**LOST に倒さない**。
 * 「落札したのに敗北通知」は取引の開始に気づかないまま放置する事故になり、
 * 相手も落札者もこちらの沈黙を待つ。UNKNOWN は呼び側で人間に上げる。
 *
 * ⚠️ 終了前のページにも「最高額入札者」は出る。この判定は
 * **終了後(isClosed)にだけ**呼ぶこと。終了前に呼ぶと「今のところ最高額」を
 * 「落札した」と読む。
 */
export function bidHistoryVerdict(input: BidHistoryInput): {
  verdict: ResultVerdict;
  reason: string;
} {
  const myName = input.myDisplayName.trim();
  if (myName === "") {
    // ログイン名が読めない = セッションが切れている可能性が高い。
    // 「自分の行が無い」と区別が付かないので、ここで別扱いにして返す。
    return { verdict: "UNKNOWN", reason: "ログイン中の表示名を読めなかった" };
  }

  const rows = input.rows.map((r) => r.replace(/\s+/g, " ").trim()).filter((r) => r !== "");
  const bidderRows = rows.filter((r) => r.includes(BIDDER_ROW_MARK));
  if (bidderRows.length === 0) {
    return { verdict: "UNKNOWN", reason: "入札履歴の行を1件も読めなかった" };
  }

  const mine = bidderRows.filter((r) => r.includes(myName));
  if (mine.length === 0) {
    return { verdict: "UNKNOWN", reason: `入札履歴に自分(${myName})の行が無い` };
  }
  if (mine.length > 1) {
    // 表示名が他の行の文字列にも含まれている等。どれが自分か決められない以上、
    // 片方に賭けるより人間に上げる。
    return {
      verdict: "UNKNOWN",
      reason: `自分(${myName})に一致する行が${mine.length}件あり特定できない`,
    };
  }

  return mine[0]!.includes(HIGHEST_BIDDER_MARK)
    ? { verdict: "WON", reason: `自分の行に「${HIGHEST_BIDDER_MARK}」が付いている` }
    : { verdict: "LOST", reason: `自分の行に「${HIGHEST_BIDDER_MARK}」が付いていない` };
}
