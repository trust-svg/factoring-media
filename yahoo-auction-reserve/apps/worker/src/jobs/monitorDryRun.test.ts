import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// monitor.ts は prisma / BullMQ / Playwright を直に握っているので実行して
// 確かめられない。ここでは **分岐の並び順** だけをソース上で固定する。
//
// なぜ順序を守る必要があるか:
//   DRY_RUN は「失敗」ではないが `outcome !== "SUCCESS"` は満たす。
//   先に `!== "SUCCESS"` 側に入ると、テスト実行がリトライされ、
//   2回目も DRY_RUN なので最終的に FAILED になる。
//   = 経路は全部正常に動いたのに「入札に失敗しました」と通知が飛ぶ。
// 早期 return の後ろにガードを置いて無効化する事故は繰り返し起きているので、
// 落ちる形で残しておく。
const SRC = readFileSync(join(__dirname, "monitor.ts"), "utf8");

describe("monitor の DRY_RUN 分岐", () => {
  it("`!== \"SUCCESS\"`(リトライ)より前に置かれている", () => {
    const dryRunAt = SRC.indexOf('result.outcome === "DRY_RUN"');
    const retryAt = SRC.indexOf('result.outcome !== "SUCCESS"');
    assert.notEqual(dryRunAt, -1, "DRY_RUN の分岐が無い");
    assert.notEqual(retryAt, -1, "リトライの分岐が無い");
    assert.ok(
      dryRunAt < retryAt,
      "DRY_RUN の分岐がリトライ分岐より後ろにある(テスト実行が FAILED になる)",
    );
  });

  it("入札の呼び出しは全て予約の dryRun を渡している", () => {
    const calls = SRC.match(/placeBid\(/g)?.length ?? 0;
    const passed = SRC.match(/dryRun: reservation\.dryRun/g)?.length ?? 0;
    assert.equal(calls, 2, "placeBid の呼び出し数が変わった(渡し漏れを確認すること)");
    assert.equal(passed, calls, "dryRun を渡していない placeBid 呼び出しがある");
  });

  it("テスト実行の結果は必ず通知する(静かに終わると動いていない場合と区別が付かない)", () => {
    const branch = SRC.slice(SRC.indexOf('result.outcome === "DRY_RUN"'));
    const end = branch.indexOf("\n    }\n");
    assert.ok(branch.slice(0, end).includes('notifyUser(reservation.userId, "DRY_RUN"'));
  });

  it("テスト実行を WON/LOST にしない(入札していないので落札結果ではない)", () => {
    const branch = SRC.slice(SRC.indexOf('result.outcome === "DRY_RUN"'));
    const end = branch.indexOf("\n    }\n");
    const body = branch.slice(0, end);
    assert.ok(body.includes('status: "DRY_RUN"'), "status を DRY_RUN にしていない");
    assert.ok(!body.includes('"WON"') && !body.includes('"LOST"'));
  });
});
