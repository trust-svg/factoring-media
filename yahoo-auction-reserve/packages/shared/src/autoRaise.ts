// 自動増額の金額計算(設計追補 2026-08-25)。
//
// ⚠️ この関数は**間違える方向が非対称**。少なく出す分は取り逃すだけだが、
// 天井を超えて出すと実際に払う金額が予算を超える。等価なつもりの
// リファクタで危険側へ倒れやすいので、敵対的な入力のテストを必ず伴わせること。

export interface AutoRaiseConfig {
  /** OFF なら増額しない */
  mode: "OFF" | "AUTO" | "APPROVAL";
  /** 1回あたりの増額幅(円) */
  step: number | null | undefined;
  /** 増額の回数上限 */
  maxCount: number | null | undefined;
  /** これまでに増額した回数 */
  usedCount: number;
  /** 絶対に超えない天井(円) */
  absoluteMax: number | null | undefined;
}

export type RaiseDecision =
  | {
      raise: false;
      reason:
        | "MODE_OFF"
        | "COUNT_EXHAUSTED"
        | "AT_CEILING"
        | "MISCONFIGURED"
        /** 天井まで上げても現在価格を上回れない = 上げても勝てない */
        | "BELOW_REQUIRED";
    }
  | { raise: true; nextAmount: number; needsApproval: boolean };

/**
 * 高値更新されたときに、次にいくらで入札しなおすかを決める。
 *
 * 返す `nextAmount` は **absoluteMax を絶対に超えない**。
 * step を足すと天井を超える場合は、天井ちょうどまで引き上げる
 * (「超えるから増額しない」にすると、あと1円で勝てる場面を落とす)。
 *
 * `minimumRequired` は「これ以上出さないと現在価格を上回れない」額
 * (`minimumBidToBeat(currentPrice)`)。step ぶん足しただけではここに届かない
 * ことがあり、そのまま出すと **増額回数だけ消費して必ず負ける**。
 * 届かないなら増額せず BELOW_REQUIRED を返す。逆に step より大きく必要な
 * ときは、天井の範囲でそこまで一気に引き上げる。
 */
export function decideRaise(
  currentAmount: number,
  cfg: AutoRaiseConfig,
  minimumRequired?: number | null,
): RaiseDecision {
  if (cfg.mode === "OFF") return { raise: false, reason: "MODE_OFF" };

  // 設定が欠けているときは増額しない。既定値で補うと、UI で入れ忘れた上限が
  // 勝手に決まってしまう(この関数の既定値は必ず「増額しない」側に倒す)。
  if (
    cfg.step == null ||
    cfg.maxCount == null ||
    cfg.absoluteMax == null ||
    !Number.isFinite(cfg.step) ||
    !Number.isFinite(cfg.maxCount) ||
    !Number.isFinite(cfg.absoluteMax) ||
    cfg.step <= 0 ||
    cfg.maxCount <= 0
  ) {
    return { raise: false, reason: "MISCONFIGURED" };
  }

  if (cfg.usedCount >= cfg.maxCount) return { raise: false, reason: "COUNT_EXHAUSTED" };
  if (currentAmount >= cfg.absoluteMax) return { raise: false, reason: "AT_CEILING" };

  const required =
    minimumRequired != null && Number.isFinite(minimumRequired) ? minimumRequired : null;

  const target = required != null
    ? Math.max(currentAmount + cfg.step, required)
    : currentAmount + cfg.step;
  const nextAmount = Math.min(target, cfg.absoluteMax);

  // Math.min を通した後でも、入力が壊れていれば天井超えはありうる
  // (currentAmount が既に天井超過など)。ここで最後に断言する。
  if (nextAmount > cfg.absoluteMax) return { raise: false, reason: "AT_CEILING" };
  if (nextAmount <= currentAmount) return { raise: false, reason: "AT_CEILING" };
  // 天井で頭打ちになった結果、必要額に届かないなら上げても負ける。
  // ここで増額しておくと回数だけ減り、次の高値更新で打つ手が無くなる。
  if (required != null && nextAmount < required) {
    return { raise: false, reason: "BELOW_REQUIRED" };
  }

  return { raise: true, nextAmount, needsApproval: cfg.mode === "APPROVAL" };
}
