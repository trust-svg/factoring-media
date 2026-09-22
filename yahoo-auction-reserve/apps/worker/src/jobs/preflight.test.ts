import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { monitorLeadSeconds, PREFLIGHT_LEAD_MS } from "@yar/shared";
import type { SessionStatusKey } from "@yar/shared/labels";
import { selectPreflightActions, type PreflightCandidate } from "./preflight";

const END = new Date("2026-09-22T22:00:00+09:00");
const SNIPE = 30;
const monitorStart = END.getTime() - monitorLeadSeconds(SNIPE) * 1000;
/** 窓の内側の時刻(monitor 起動の30分前) */
const INSIDE = new Date(monitorStart - 30 * 60 * 1000);
/** 窓の外の時刻 */
const OUTSIDE = new Date(monitorStart - PREFLIGHT_LEAD_MS - 1000);

function row(id: string, status: SessionStatusKey = "ACTIVE"): PreflightCandidate {
  return {
    id,
    endAt: END,
    snipeSecondsBefore: SNIPE,
    sessionStatus: status,
    sessionLastVerifiedAt: null,
  };
}

describe("事前確認の対象選別", () => {
  it("窓の外の予約は選ばない", () => {
    // ⚠️ ここで選ぶと「確認済み」の印が窓に入る前に立ち、
    //    本当に見るべき時刻には対象から外れている
    assert.deepEqual(selectPreflightActions([row("r1")], OUTSIDE, 2), []);
  });

  it("窓に入ったら開いて確かめる", () => {
    assert.deepEqual(selectPreflightActions([row("r1")], INSIDE, 2), [
      { id: "r1", kind: "verify" },
    ]);
  });

  it("ブラウザ枠の分だけ確認する", () => {
    const got = selectPreflightActions([row("r1"), row("r2"), row("r3")], INSIDE, 2);
    assert.deepEqual(got, [
      { id: "r1", kind: "verify" },
      { id: "r2", kind: "verify" },
    ]);
  });

  it("枠から溢れた予約は選ばない(印を付けずに次の走査へ回す)", () => {
    // ⚠️ ここで選んでしまうと、印だけ立って一度も確認されない予約ができる。
    //    しかも「確認済み」に見えるので、二度と対象にならない
    const got = selectPreflightActions([row("r1"), row("r2"), row("r3")], INSIDE, 2);
    assert.equal(
      got.find((a) => a.id === "r3"),
      undefined,
    );
  });

  it("死んでいる連携の通知はブラウザ枠を使わない", () => {
    // 通知にブラウザは要らない。枠に数えると、死んだ連携が並んだ日に
    // 後ろの予約が「枠切れ」で黙って落ちる
    const rows = [row("d1", "EXPIRED"), row("d2", "REVOKED"), row("r1"), row("r2")];
    assert.deepEqual(selectPreflightActions(rows, INSIDE, 2), [
      { id: "d1", kind: "notify-dead" },
      { id: "d2", kind: "notify-dead" },
      { id: "r1", kind: "verify" },
      { id: "r2", kind: "verify" },
    ]);
  });

  it("ブラウザ枠が0でも、死んでいる連携は必ず通知する", () => {
    assert.deepEqual(selectPreflightActions([row("d1", "EXPIRED")], INSIDE, 0), [
      { id: "d1", kind: "notify-dead" },
    ]);
  });

  it("開かずに済む判定(trust / too-late)も枠を使わない", () => {
    const trusted: PreflightCandidate = {
      ...row("t1"),
      sessionLastVerifiedAt: new Date(INSIDE.getTime() - 1000),
    };
    const got = selectPreflightActions([trusted, row("r1"), row("r2")], INSIDE, 2);
    assert.deepEqual(got, [
      { id: "t1", kind: "trust" },
      { id: "r1", kind: "verify" },
      { id: "r2", kind: "verify" },
    ]);
  });

  it("入力の順序を保つ(終了が近い予約を先に処理する)", () => {
    const rows = [row("r1"), row("d1", "EXPIRED"), row("r2")];
    assert.deepEqual(
      selectPreflightActions(rows, INSIDE, 5).map((a) => a.id),
      ["r1", "d1", "r2"],
    );
  });
});
