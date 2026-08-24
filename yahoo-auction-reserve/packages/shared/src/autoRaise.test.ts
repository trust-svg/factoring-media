import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { decideRaise, type AutoRaiseConfig } from "./autoRaise";

const base: AutoRaiseConfig = {
  mode: "AUTO",
  step: 500,
  maxCount: 3,
  usedCount: 0,
  absoluteMax: 10_000,
};

describe("decideRaise", () => {
  it("OFF なら常に増額しない", () => {
    const d = decideRaise(1000, { ...base, mode: "OFF" });
    assert.equal(d.raise, false);
  });

  it("通常は step ぶん増額する", () => {
    const d = decideRaise(1000, base);
    assert.equal(d.raise, true);
    assert.equal(d.raise && d.nextAmount, 1500);
  });

  it("APPROVAL では承認が要ると伝える", () => {
    const d = decideRaise(1000, { ...base, mode: "APPROVAL" });
    assert.equal(d.raise && d.needsApproval, true);
  });

  it("AUTO では承認を要求しない", () => {
    const d = decideRaise(1000, base);
    assert.equal(d.raise && d.needsApproval, false);
  });

  it("回数を使い切ったら増額しない", () => {
    const d = decideRaise(1000, { ...base, usedCount: 3 });
    assert.equal(d.raise, false);
    assert.equal(!d.raise && d.reason, "COUNT_EXHAUSTED");
  });

  // --- 天井まわり(危険側に倒れるのはここ) ---

  it("step を足すと天井を超える場合は、天井ちょうどで止める", () => {
    const d = decideRaise(9800, base); // 9800 + 500 = 10300 > 10000
    assert.equal(d.raise, true);
    assert.equal(d.raise && d.nextAmount, 10_000);
  });

  it("既に天井に達していたら増額しない", () => {
    const d = decideRaise(10_000, base);
    assert.equal(d.raise, false);
    assert.equal(!d.raise && d.reason, "AT_CEILING");
  });

  it("既に天井を超えている壊れた状態でも、さらに上げない", () => {
    const d = decideRaise(12_000, base);
    assert.equal(d.raise, false);
  });

  it("どんな入力でも天井を超える額は返さない(総当り)", () => {
    const ceilings = [1, 100, 999, 1000, 10_000, 123_456];
    const steps = [1, 7, 500, 9999, 1_000_000];
    const currents = [0, 1, 99, 500, 999, 1000, 9999, 10_000, 999_999];
    for (const absoluteMax of ceilings) {
      for (const step of steps) {
        for (const currentAmount of currents) {
          for (const mode of ["AUTO", "APPROVAL"] as const) {
            const d = decideRaise(currentAmount, {
              mode,
              step,
              maxCount: 99,
              usedCount: 0,
              absoluteMax,
            });
            if (d.raise) {
              assert.ok(
                d.nextAmount <= absoluteMax,
                `天井超過: current=${currentAmount} step=${step} max=${absoluteMax} → ${d.nextAmount}`,
              );
              assert.ok(
                d.nextAmount > currentAmount,
                `増額になっていない: current=${currentAmount} → ${d.nextAmount}`,
              );
            }
          }
        }
      }
    }
  });

  // --- 設定漏れは「増額しない」側へ倒れること ---

  it("設定が欠けていたら増額しない(既定値で補わない)", () => {
    const missing: Array<Partial<AutoRaiseConfig>> = [
      { step: null },
      { maxCount: null },
      { absoluteMax: null },
      { step: undefined },
      { absoluteMax: undefined },
      { step: 0 },
      { step: -100 },
      { maxCount: 0 },
      { step: Number.NaN },
      { absoluteMax: Number.NaN },
      { step: Number.POSITIVE_INFINITY },
      { absoluteMax: Number.POSITIVE_INFINITY },
    ];
    for (const patch of missing) {
      const d = decideRaise(1000, { ...base, ...patch });
      assert.equal(
        d.raise,
        false,
        `${JSON.stringify(patch)} で増額してしまった`,
      );
    }
  });
});
