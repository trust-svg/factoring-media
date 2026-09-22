/**
 * 入札予約をユーザーの操作でキャンセルしてよいかの判定。
 *
 * ヤフオクの入札は取り消せない。だからここで見るのは「予約の状態」ではなく
 * **すでに自分の入札が外に出てしまっているか** で、状態はその代理指標に過ぎない。
 *
 * ⚠️ status だけでは判定できない。自動延長で再スナイプする回、monitor は
 * 入札に成功したあとで status を MONITORING に**戻す**
 * (apps/worker/src/jobs/monitor.ts の自動延長ブロック)。
 * つまり MONITORING は「まだ入札していない」を意味しない。
 * 入札済みかどうかは BidAttempt に SUCCESS があるかで見る。
 *
 * ⚠️ BIDDING は SUCCESS の記録が無くても断る。placeBid が通ったあと
 * BidAttempt を書く前にプロセスが落ちる窓があり、「記録が無い = 入札していない」
 * とは言えない(同じ理由で jobs/stuck.ts の needsResultCheck も BIDDING を見に行く)。
 * 誤って断る代償は「あと数分待って結果を見る」だけだが、誤って許す代償は
 * 「入札済みなのにキャンセル扱いで安心し、落札していることに気付かない」。
 */
export type CancelRefusal = "ALREADY_BID" | "IN_FLIGHT" | "FINISHED";

export interface CancelVerdict {
  ok: boolean;
  refusal?: CancelRefusal;
  /** UI・API レスポンスにそのまま出す日本語。断る理由は必ず埋める */
  message: string;
}

/** キャンセルを受け付ける状態。それ以外は決着済みとして断る */
const CANCELABLE_STATUS = ["SCHEDULED", "MONITORING"] as const;

export function cancelVerdict(row: {
  status: string;
  /** その予約に outcome=SUCCESS の BidAttempt があるか */
  hasSuccessfulBid: boolean;
}): CancelVerdict {
  if (row.hasSuccessfulBid) {
    return {
      ok: false,
      refusal: "ALREADY_BID",
      message: "すでに入札済みです。ヤフオクの入札は取り消せないためキャンセルできません",
    };
  }
  if (row.status === "BIDDING") {
    return {
      ok: false,
      refusal: "IN_FLIGHT",
      message: "入札処理の実行中です。結果が出るまでキャンセルできません",
    };
  }
  if ((CANCELABLE_STATUS as readonly string[]).includes(row.status)) {
    return { ok: true, message: "" };
  }
  return {
    ok: false,
    refusal: "FINISHED",
    message: "すでに終了している予約です",
  };
}
