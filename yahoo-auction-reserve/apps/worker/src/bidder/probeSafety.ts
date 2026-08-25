// 「押すつもりの無いボタンを押してしまった」を防ぐ判定。
//
// 使うのは2箇所:
//   - P0 プローブ(scripts/p0-probe.ts)の Stage 2 → confirmClickVerdict
//   - 本番の入札(bidder/placeBid.ts)の確定直前   → submitTargetVerdict
//
// なぜ要るか: Stage 2 は実商品に実額を入れた状態で確認ボタンを押す。
// その「確認ボタン」は未検証のセレクタで選ばれる。つまりスクリプト冒頭の
// 「最終確定ボタンは絶対に押さない」という保証は、**P0 でこれから確かめる
// はずのセレクタが正しいこと** に依存していて、循環している。
//
// ⚠️ 判定は「分からないなら押さない」側に倒す。誤検知の代償は
// 「P0 をもう一度手で進める」だけだが、見逃しの代償は **本物の入札が飛ぶ**
// (取り消せない)。非対称なので、疑わしきは止める。

/** 確認ボタンとして押してよいかの判定 */
export interface ConfirmClickVerdict {
  safe: boolean;
  reason: string;
}

/** 確認ボタンのラベルに入っているべき語。これが無いものは押さない */
const CONFIRM_WORD = "確認";
/** 押した瞬間に入札が確定しうる語 */
const SUBMIT_WORD = "入札する";

export function confirmClickVerdict(args: {
  /** 押そうとしている要素の同一性キー(describeNode の nodeKey) */
  confirmKey: string;
  /** 確定ボタン候補に当たった要素すべての同一性キー */
  submitKeys: string[];
  /** 押そうとしている要素の表示テキスト or value */
  label: string;
}): ConfirmClickVerdict {
  const { confirmKey, submitKeys, label } = args;

  // 1. 確定ボタン候補と同じ要素なら、押した瞬間に入札が飛ぶ。
  //    キーが偶然一致した別要素でも止まるが、それは安全側の誤検知。
  if (submitKeys.includes(confirmKey)) {
    return {
      safe: false,
      reason: "確定ボタン候補と同一の要素に当たっている(押すと実入札になる)",
    };
  }

  // 2. 「確認」の語が無いものは確認ボタンとして扱わない。
  //    これは `[data-testid="bid-confirm"]` のような **未検証のプレースホルダ**
  //    が想定外の要素を掴んだ場合を狙って止めるための条件。
  if (!label.includes(CONFIRM_WORD)) {
    return {
      safe: false,
      reason: `ラベルに「${CONFIRM_WORD}」が無い(${JSON.stringify(label)})`,
    };
  }

  // 3. 「確認」と「入札する」が両方入っているものは、
  //    「入札内容を確認して入札する」型の1段確定ボタンでありうる。
  //    2 の条件を通ってしまうので、ここで別途落とす。
  if (label.includes(SUBMIT_WORD)) {
    return {
      safe: false,
      reason: `ラベルに「${SUBMIT_WORD}」が含まれる(1段で確定する可能性がある: ${JSON.stringify(label)})`,
    };
  }

  return { safe: true, reason: "" };
}


/**
 * 確定ボタンを押す直前の最終ガード。
 *
 * なぜ要るか: selectors.bidSubmitButton は selectors.bidButton と
 * **文字列が同一**(どちらも `role=button[name="入札する"]`)。
 * 確認画面の確定ボタンの表示テキストが未確認なので、当てずっぽうの別文言を
 * 置くより同一のまま残す判断をした(selectors.ts の地雷7)。
 *
 * その結果、確認ボタンのクリックが遷移を起こさなかった場合、
 * placeBid は **商品ページに残ったまま入札フォームを開くボタンを押し**、
 * それを「確定した」と解釈して SUCCESS を返してしまう。
 * 入札していないのに成功と報告する = 予約が空振りしても誰も気づかない。
 *
 * ⚠️ 止めるのは安全側。誤検知の代償は「1件入札できずに失敗通知が飛ぶ」で、
 * 見逃しの代償は「入札できていないのに成功と報告される」。後者の方が悪い。
 */
export interface SubmitTargetVerdict {
  safe: boolean;
  reason: string;
}

export function submitTargetVerdict(args: {
  /** 確定ボタン候補が1つでも見つかったか */
  found: boolean;
  /** 入札ボタンを押した後、URL が変わったか */
  navigated: boolean;
  /**
   * 最初に押した「入札する」ボタンと同一要素か。
   * ⚠️ 遷移した場合は前のページの要素ハンドルが無効になるので比較できない。
   * 比較できなかったときは true(=止める)を渡すこと。navigated=true なら
   * この値は見ない。
   */
  sameAsBidButton: boolean;
}): SubmitTargetVerdict {
  if (!args.found) {
    return {
      safe: false,
      reason: "確定ボタンが見つからない(確認画面に着いていない可能性がある)",
    };
  }
  // 別ページに移っているなら、商品ページの「入札する」ボタンはもう存在しない。
  // 同一要素になりようがないので、ここで通す。
  // (要素の同一性比較は遷移をまたぐと必ず失敗するため、順序が逆だと
  //  正常な入札が全部止まる)
  if (args.navigated) {
    return { safe: true, reason: "" };
  }
  if (args.sameAsBidButton) {
    return {
      safe: false,
      reason:
        "確定ボタンが最初の「入札する」ボタンと同一要素。" +
        "確認画面に遷移しておらず、商品ページに留まっている",
    };
  }
  return { safe: true, reason: "" };
}
