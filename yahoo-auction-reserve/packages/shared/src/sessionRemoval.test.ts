import assert from "node:assert/strict";
import test from "node:test";
import { planSessionRemoval } from "./sessionRemoval";

test("予約もウォッチも無い連携は物理削除する", () => {
  const plan = planSessionRemoval({ reservations: 0, watchlistItems: 0 });
  assert.equal(plan.mode, "delete");
});

test("予約が残っている連携は削除せず解除にする", () => {
  // ⚠️ 落札履歴は消せない。物理削除は外部キー(RESTRICT)に弾かれる
  const plan = planSessionRemoval({ reservations: 17, watchlistItems: 0 });
  assert.equal(plan.mode, "revoke");
});

test("ウォッチ商品だけが残っている連携も解除にする", () => {
  const plan = planSessionRemoval({ reservations: 0, watchlistItems: 101 });
  assert.equal(plan.mode, "revoke");
});

test("解除の理由に残った件数を書く(消えなかった理由が画面で分かるように)", () => {
  const plan = planSessionRemoval({ reservations: 17, watchlistItems: 101 });
  assert.equal(plan.mode, "revoke");
  const reason = plan.mode === "revoke" ? plan.reason : "";
  assert.match(reason, /17/);
  assert.match(reason, /101/);
});

test("残っていない側は理由に書かない", () => {
  const plan = planSessionRemoval({ reservations: 3, watchlistItems: 0 });
  const reason = plan.mode === "revoke" ? plan.reason : "";
  assert.match(reason, /予約/);
  assert.equal(/ウォッチ/.test(reason), false);
});
