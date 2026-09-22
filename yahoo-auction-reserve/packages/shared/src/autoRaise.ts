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

// ---- 入力バリデーション ---------------------------------------------------

/** 1回の増額幅の下限。ヤフオクの最小入札単位より小さい増額は意味を持たない。 */
export const AUTO_RAISE_STEP_MIN = 10;
/** 増額回数の上限。青天井にすると絶対上限まで一気に到達する。 */
export const AUTO_RAISE_MAX_COUNT_LIMIT = 20;

export type AutoRaiseMode = "OFF" | "AUTO" | "APPROVAL";

export interface AutoRaiseFields {
  autoRaiseMode: AutoRaiseMode;
  autoRaiseStep: number | null;
  autoRaiseMaxCount: number | null;
  absoluteMaxAmount: number | null;
}

export type AutoRaiseValidation =
  | { ok: true; value: AutoRaiseFields }
  | { ok: false; error: string };

function asInt(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : null;
}

/**
 * 予約の自動増額設定を検証して、DB へ入れる形に正規化する。
 *
 * ⚠️ **足りない項目を既定値で補わない**。ここで step や絶対上限を勝手に決めると、
 * 入れ忘れた予算が黙って設定され、上限額を超えた入札が「設定どおり」として通る。
 * 欠けていたらエラーにして、増額しない側でもなく **登録させない**。
 *
 * OFF のときは関連項目を全て null に落とす。残したままにすると、OFF に戻した
 * つもりの予約に古い絶対上限が残り、あとで AUTO に切り替えた瞬間に
 * 意図しない金額で増額が走る。
 */
export function validateAutoRaiseInput(
  input: {
    autoRaiseMode?: unknown;
    autoRaiseStep?: unknown;
    autoRaiseMaxCount?: unknown;
    absoluteMaxAmount?: unknown;
  },
  maxBidAmount: number,
): AutoRaiseValidation {
  const rawMode = input.autoRaiseMode ?? "OFF";
  if (rawMode !== "OFF" && rawMode !== "AUTO" && rawMode !== "APPROVAL") {
    return { ok: false, error: "自動増額の設定値が不正です" };
  }
  const mode: AutoRaiseMode = rawMode;

  if (mode === "OFF") {
    return {
      ok: true,
      value: {
        autoRaiseMode: "OFF",
        autoRaiseStep: null,
        autoRaiseMaxCount: null,
        absoluteMaxAmount: null,
      },
    };
  }

  const absoluteMaxAmount = asInt(input.absoluteMaxAmount);
  const autoRaiseStep = asInt(input.autoRaiseStep);
  const autoRaiseMaxCount = asInt(input.autoRaiseMaxCount);

  if (absoluteMaxAmount == null || absoluteMaxAmount <= maxBidAmount) {
    return {
      ok: false,
      error: `絶対上限は上限額(${maxBidAmount}円)より高い整数で指定してください`,
    };
  }
  if (autoRaiseStep == null || autoRaiseStep < AUTO_RAISE_STEP_MIN) {
    return {
      ok: false,
      error: `1回あたりの増額幅は${AUTO_RAISE_STEP_MIN}円以上で指定してください`,
    };
  }
  if (
    autoRaiseMaxCount == null ||
    autoRaiseMaxCount < 1 ||
    autoRaiseMaxCount > AUTO_RAISE_MAX_COUNT_LIMIT
  ) {
    return {
      ok: false,
      error: `増額の回数上限は1〜${AUTO_RAISE_MAX_COUNT_LIMIT}回で指定してください`,
    };
  }

  return {
    ok: true,
    value: { autoRaiseMode: mode, autoRaiseStep, autoRaiseMaxCount, absoluteMaxAmount },
  };
}
