// P0 プローブ(scripts/p0-probe.ts)の Stage 2 で、
// 「確認ボタンのつもりで押した要素が実は確定ボタンだった」を防ぐ判定。
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
