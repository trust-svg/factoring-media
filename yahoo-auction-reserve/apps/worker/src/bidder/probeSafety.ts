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
 * なぜ要るか: 入札フォームも確認画面も **モーダルで URL が変わらない**
 * (2026-08-28 実測)。つまり「遷移したから別の画面だ」という判断材料が
 * 一切無いまま、取り消せないボタンを押すことになる。
 * しかも商品ページの「入札する」ボタン2件は、確認画面が出ている間も
 * 裏の DOM に残り続ける。セレクタが少しでも緩いと、
 * **確定したつもりで裏のボタンを押して SUCCESS を返す**
 * (入札していないのに成功報告 = 予約が空振りしても誰も気づかない)。
 *
 * そこで4つ別々の根拠を要求する:
 *   1. 確定ボタンが見つかる
 *   2. 入札額の入力欄が消えている(確認画面に着いた positive な証拠)
 *   3. ラベルが商品ページ側のボタン(「入札する」/「値段を上げて入札」ちょうど)ではない
 *   4. 最初に押した入札ボタンと同一要素ではない
 *
 * ⚠️ 止めるのは安全側。誤検知の代償は「1件入札できずに失敗通知が飛ぶ」で、
 * 見逃しの代償は「入札できていないのに成功と報告される」。後者の方が悪い。
 */
export interface SubmitTargetVerdict {
  safe: boolean;
  reason: string;
}

/**
 * 商品ページの「入札フォームを開く」ボタンの表示テキスト。
 * ⚠️ 確認画面の確定ボタンは「上記のガイドライン等、情報提供に同意して 入札する」で、
 * **これとは別物**(2026-08-28 実測)。ちょうどこの文字列だけのボタンを掴んで
 * いるなら、それはモーダルの裏に残っている商品ページのボタン。
 *
 * ⚠️ 2つある。自分がその商品に入札済みだと文言が「値段を上げて入札」に
 * 変わる(2026-09-04 実測・selectors.ts の地雷15)。片方だけを弾いていると、
 * 入札済みの商品では裏のボタンがこのガードを素通りする
 * = **入札していないのに SUCCESS** に戻る。
 */
const OPEN_FORM_LABELS = ["入札する", "値段を上げて入札"] as const;

/**
 * 確定ボタンのラベルに必ず入っている語。
 * ⚠️ 「入札する」ではなく「入札」。入口が「値段を上げて入札」に変わる商品では
 * 確定側も「…同意…値段を上げて入札」になりうる(未実測)。狭いままだと、
 * 正しく掴んでいるのにここで落ちて入札が一度も成立しない。
 * 裏のボタンとの判別は上の完全一致(OPEN_FORM_LABELS)が担当する。
 */
const SUBMIT_LABEL_WORD = "入札";

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
  /**
   * 確認ボタンを押した後も入札額の入力欄が残っているか。
   * ⚠️ 2026-08-28 実測: 確認画面に進むと `#inputPrice` は DOM から消える
   * (input 12個 → 11個)。URL は変わらないので、**入力欄の消滅が
   * 「確認画面に着いた」ことの唯一の positive な証拠**。
   */
  formStillOpen: boolean;
  /** 押そうとしているボタンの表示テキスト */
  label: string;
}): SubmitTargetVerdict {
  if (!args.found) {
    return {
      safe: false,
      reason: "確定ボタンが見つからない(確認画面に着いていない可能性がある)",
    };
  }
  // 入力欄が残っている = まだ入札フォームのモーダル。
  // ここで押せるものは全部「フォームを開く/送る」側のボタンで、確定ボタンではない。
  if (args.formStillOpen) {
    return {
      safe: false,
      reason: "入札額の入力欄がまだある(確認画面に進んでいない)",
    };
  }
  // ラベルが「入札する」ちょうどなら、それは商品ページ側のボタン。
  // ⚠️ 同一要素判定(sameAsBidButton)は最初に押した1つとしか比較しない。
  //    商品ページには「入札する」が2つあるので、**もう片方を掴むと
  //    同一要素判定をすり抜ける**。ラベルで落とすのはその穴を塞ぐため。
  const trimmed = args.label.trim();
  if ((OPEN_FORM_LABELS as readonly string[]).includes(trimmed)) {
    return {
      safe: false,
      reason: `ラベルが「${trimmed}」ちょうど(商品ページ側のボタンを掴んでいる)`,
    };
  }
  // 文言が変わったときは、当てずっぽうで押さずに止める。
  // 誤検知の代償は「入札できずに失敗通知」、見逃しの代償は「意図しない操作」。
  if (!args.label.includes(SUBMIT_LABEL_WORD)) {
    return {
      safe: false,
      reason: `ラベルに「${SUBMIT_LABEL_WORD}」が無い(${JSON.stringify(args.label)})`,
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
