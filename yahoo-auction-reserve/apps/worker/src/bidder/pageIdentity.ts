// 「中身が読めなかった」の理由を割る判定。
//
// なぜ要るか(2026-08-26 実測で判明):
//   WATCHLIST_URL_CANDIDATES に入れていた2つの URL は、**どちらも存在しな
//   かった**。ヤフオクの404ページはヘッダーと「カテゴリから探す」の30リンク
//   とフッターを持っているので、クリック要素が 51〜55個ある。つまり
//   pageReady.ts の描画判定(閾値5)は素通りし、「描画は完了している」と出る。
//   その上で商品リンクだけが0件になるため、
//
//       描画済み ＋ ログイン壁なし ＋ 商品0件
//
//   という、**ウォッチリストが空の状態と見分けの付かない** 姿になっていた。
//   実際、ログイン時と未ログインで出力がほぼ同じ(55要素 vs 51要素)になり、
//   「未ログインなのにログイン画面へ飛ばされない」という最大の手掛かりまで
//   「ログイン不要のページなのだろう」で流せてしまう状態だった。
//
// ⚠️ 404 を「空」と読むと、同期は毎回 **成功の顔で0件** を返し、予約候補が
//    永久に増えないまま誰も気づかない。存在しない URL は「空」ではない。
//
// ⚠️ HTTP ステータスだけに頼らない。ヤフオクがこの案内ページを 200 で返す
//    (ソフト404)かどうかは未確認で、逆に本文の文言はいつ変わってもおかしく
//    ない。**どちらか一方が当たれば NOT_FOUND** にして、片方が黙って効かなく
//    なっても検知が生き残るようにする。

export type PageIdentity =
  /** 存在しない URL(ヤフオクの案内ページに着いた) */
  | "NOT_FOUND"
  /** ログイン画面に飛ばされた */
  | "LOGIN_REQUIRED"
  /** 上のどちらでもない = 中身のあるページとして扱ってよい */
  | "CONTENT";

export interface PageIdentityVerdict {
  kind: PageIdentity;
  reason: string;
}

/**
 * ヤフオクの404案内ページの本文に出る語(2026-08-26 スクリーンショットで確認)。
 * 実際の表示は「指定されたURLのページは存在しません。」。
 * URL の書き方の揺れを避けるため、後半だけを見る。
 */
export const NOT_FOUND_PHRASE = "ページは存在しません";

/** ログイン画面のホスト */
export const LOGIN_HOST = "login.yahoo.co.jp";

export function pageIdentityVerdict(args: {
  /** 最終的に着いた URL */
  url: string;
  /** page.goto() の応答ステータス。取れなかったときは null */
  httpStatus: number | null;
  /** ページ本文のテキスト(innerText 相当) */
  bodyText: string;
}): PageIdentityVerdict {
  const { url, httpStatus, bodyText } = args;

  // ログイン画面に着いたかは URL で確実に分かる。404 案内ページが
  // ログイン画面へ飛ぶことは無いので、先に見てよい。
  if (url.includes(LOGIN_HOST)) {
    return { kind: "LOGIN_REQUIRED", reason: `ログイン画面に飛ばされている(${url})` };
  }

  if (httpStatus === 404) {
    return { kind: "NOT_FOUND", reason: `HTTP 404 が返っている(${url})` };
  }

  if (bodyText.includes(NOT_FOUND_PHRASE)) {
    return {
      kind: "NOT_FOUND",
      reason:
        `本文に「${NOT_FOUND_PHRASE}」がある(${url})。` +
        `HTTP ステータスは ${httpStatus ?? "不明"} なので、ソフト404`,
    };
  }

  return { kind: "CONTENT", reason: "" };
}
