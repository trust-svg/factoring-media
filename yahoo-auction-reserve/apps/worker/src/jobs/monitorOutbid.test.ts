import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// 「入札後に高値更新されたら追加入札できる」を成立させている条件を、
// ソース上で固定する。monitor.ts は prisma / BullMQ / Playwright を直に
// 握っていて実行して確かめられないので、monitorDryRun.test.ts と同じやり方。
//
// ここで守っているのは全部 **黙って壊れる** 種類の条件で、壊れても
// 例外もログも出ず「増額したのに入札されない」だけが起きる。
const SRC = readFileSync(join(__dirname, "monitor.ts"), "utf8");
const LOOP = SRC.slice(SRC.indexOf("async function snipeLoop("));

describe("自動延長ループでの増額", () => {
  it("承認制の増額を延長ループで聞ける(allowApproval を false で固定しない)", () => {
    // false 固定だと、5分近く猶予がある自動延長後でも承認を出せず、
    // 承認制を選んでいる人は高値更新にまったく対応できない。
    assert.ok(
      LOOP.includes("allowApproval: true"),
      "tryAutoRaise に allowApproval: true を渡していない",
    );
    assert.ok(
      !SRC.includes("allowApproval: false"),
      "allowApproval: false が残っている(延長ループで承認を出せない)",
    );
  });

  it("終了時刻を書き換えたら、必ずメモリ側の reservation.endAt も合わせる", () => {
    // tryAutoRaise は reservation.endAt から承認の締切を計算する。
    // ここがズレると締切が常に過去になり、承認制の増額が一度も成立しない
    // (しかも DECLINED: NO_TIME に化けるので原因が分からない)。
    const reassigns = LOOP.match(/^\s*endAt = /gm)?.length ?? 0;
    const syncs = LOOP.match(/^\s*reservation\.endAt = endAt;/gm)?.length ?? 0;
    assert.ok(reassigns > 0, "endAt の再代入が見つからない(構造が変わった)");
    assert.equal(syncs, reassigns, "endAt を書き換えてメモリ側を合わせていない箇所がある");
  });
});

describe("走行中の増額の取り込み", () => {
  it("入札の直前に予約を読み直している", () => {
    // 「高値更新されました」を見て上限を上げるのは、待っている **最中**。
    // 待つ前の値のまま入札すると、増額したのに古い額で入札して必ず負ける
    // (しかも入札自体は通るので SUCCESS と報告される)。
    const sleepAt = LOOP.indexOf("await sleepUntil(snipeAt)");
    const bidAt = LOOP.indexOf("await placeBid(");
    assert.ok(sleepAt !== -1 && bidAt !== -1, "待機または入札の呼び出しが見つからない");
    const between = LOOP.slice(sleepAt, bidAt);
    assert.ok(
      between.includes("syncReservation(reservation)"),
      "スナイプ待機のあと、入札までの間に予約を読み直していない",
    );
  });

  it("読み直しは上限額を DB の値で上書きしている", () => {
    const fn = SRC.slice(SRC.indexOf("async function syncReservation("));
    assert.ok(
      /Object\.assign\(reservation, fresh/.test(fn.slice(0, fn.indexOf("\n}"))),
      "syncReservation が取得した行を反映していない",
    );
  });
});

describe("入札後に上限を超えたときの身の振り方", () => {
  it("未入札のときだけ EXPIRED で降りる", () => {
    const at = LOOP.indexOf('status: "EXPIRED"');
    assert.notEqual(at, -1, "EXPIRED にする分岐が無い");
    const before = LOOP.slice(0, at);
    const GUARD = "} else if (!hasBid) {";
    const guard = before.lastIndexOf(GUARD);
    assert.notEqual(guard, -1, "EXPIRED の分岐が !hasBid で守られていない");
    // ガードと EXPIRED の間に別の分岐が挟まっていない = 本当にこの分岐の中
    assert.ok(
      !before.slice(guard + GUARD.length).includes("} else"),
      "EXPIRED が !hasBid 以外の分岐に移っている",
    );
  });

  it("入札済みで見送るときは監視を降りない(結果を出さずに終わらない)", () => {
    // 降りると WON / LOST が一度も出ず、落札していても誰も気づかない。
    const at = LOOP.indexOf('outcome: "OUTBID"');
    assert.notEqual(at, -1, "見送りを記録する BidAttempt が無い");
    const branchEnd = LOOP.indexOf("\n    } else {", at);
    assert.notEqual(branchEnd, -1, "見送り分岐の終わりが見つからない");
    assert.ok(
      !LOOP.slice(at, branchEnd).includes("return"),
      "入札を見送る分岐が return している(結果通知が出ないまま終わる)",
    );
  });

  it("高値更新の通知は監視を続ける側の分岐から出している", () => {
    const notifyAt = LOOP.indexOf('notifyUser(reservation.userId, "OUTBID"');
    const expiredAt = LOOP.indexOf('status: "EXPIRED"');
    assert.notEqual(notifyAt, -1, "OUTBID の通知が無い");
    assert.ok(notifyAt > expiredAt, "OUTBID の通知が未入札の降板分岐より前にある");
  });
});
