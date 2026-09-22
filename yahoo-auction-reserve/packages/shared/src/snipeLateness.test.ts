import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { classifySnipeLateness } from "./snipeLateness";

describe("スナイプの遅れの分類", () => {
  it("許容範囲内なら ON_TIME で何も残さない", () => {
    const v = classifySnipeLateness({ lateBySec: 1, unavoidableSec: 0, loopWorkSec: 1 });
    assert.equal(v.level, "ON_TIME");
    assert.equal(v.note, null);
  });

  it("予定より早く起きた場合も ON_TIME(負の遅れは 0 に丸める)", () => {
    const v = classifySnipeLateness({ lateBySec: -2, unavoidableSec: 0, loopWorkSec: 8 });
    assert.equal(v.level, "ON_TIME");
    assert.equal(v.lateBySec, 0);
  });

  // 2026-09-20 に実測した形。snipeSecondsBefore=330・延長幅300秒で
  // snipeAt が生まれた瞬間に30秒過去 → そこへループの仕事11秒が乗って41秒。
  // この回を DELAYED にしてしまうと、結局「延長のたびに鳴る警報」が残る。
  it("自動延長ラウンドの41秒(不可避30秒 + ループ11秒)は STRUCTURAL", () => {
    const v = classifySnipeLateness({ lateBySec: 41, unavoidableSec: 30, loopWorkSec: 11 });
    assert.equal(v.level, "STRUCTURAL");
    assert.equal(v.excessSec, 0);
    assert.ok(v.note);
    // 本物の故障と読まれる文面を出さないことがこの修正の目的。
    assert.ok(!v.note!.includes("起動遅れ"));
    // ただし内訳は必ず残す(読んだ人が自分で検算できるように)。
    assert.ok(v.note!.includes("不可避分30秒"));
    assert.ok(v.note!.includes("ループ処理11秒"));
  });

  it("延長ラウンドでも、内訳で説明できない遅れが残れば DELAYED", () => {
    const v = classifySnipeLateness({ lateBySec: 90, unavoidableSec: 30, loopWorkSec: 11 });
    assert.equal(v.level, "DELAYED");
    assert.equal(v.excessSec, 49);
    assert.ok(v.note!.includes("説明不能49秒"));
  });

  // 待つ余裕があった回にループ仕事が遅れとして出たなら、それは予定を食い潰した
  // ということなので差し引かない(初回ループの起動遅れを隠さないため)。
  it("初回ループ(不可避分なし)の遅れは従来どおり起動遅れとして警告する", () => {
    const v = classifySnipeLateness({ lateBySec: 40, unavoidableSec: 0, loopWorkSec: 40 });
    assert.equal(v.level, "DELAYED");
    assert.equal(v.excessSec, 40);
    assert.ok(v.note!.includes("起動遅れ"));
  });

  // ループ仕事を無条件に免罪すると、fetchAuctionInfo のハングが正常扱いになる。
  it("ループ処理がウォームアップ予算(60秒)を超えたら内訳に関係なく DELAYED", () => {
    const v = classifySnipeLateness({ lateBySec: 400, unavoidableSec: 300, loopWorkSec: 100 });
    assert.equal(v.level, "DELAYED");
    assert.ok(v.note!.includes("ループ処理が異常に長い"));
  });

  it("不可避分が総遅れを超えて渡されても excess は負にならない", () => {
    const v = classifySnipeLateness({ lateBySec: 5, unavoidableSec: 999, loopWorkSec: 999 });
    assert.equal(v.excessSec, 0);
    assert.equal(v.unavoidableSec, 5);
  });

  it("閾値は差し替えられる", () => {
    const v = classifySnipeLateness({
      lateBySec: 300,
      unavoidableSec: 300,
      loopWorkSec: 0,
      toleranceSec: 3,
    });
    assert.equal(v.level, "STRUCTURAL");
  });
});
