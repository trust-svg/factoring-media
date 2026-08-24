import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { judgeSession, planVerifyOutcome } from "./sessionVerdict";

const base = {
  finalUrl: "https://page.auctions.yahoo.co.jp/jp/auction/x1111",
  loginLinkCount: 0,
  loggedInIndicatorCount: 1,
};

describe("judgeSession", () => {
  it("ログイン画面へのリダイレクトは失効", () => {
    const r = judgeSession({
      ...base,
      finalUrl: "https://login.yahoo.co.jp/config/login?.src=auc",
    });
    assert.equal(r.verdict, "EXPIRED");
  });

  it("リダイレクト判定はホスト部で行う(クエリに含まれるだけでは失効にしない)", () => {
    // 実測でログイン誘導 URL は .done= に元URLを持つ。逆に商品ページの
    // クエリに login.yahoo.co.jp が現れても、それは失効の証拠ではない。
    const r = judgeSession({
      ...base,
      finalUrl: "https://page.auctions.yahoo.co.jp/jp/auction/x1?ref=login.yahoo.co.jp.example.com",
    });
    assert.notEqual(r.verdict, "EXPIRED");
  });

  it("ログインリンクが出ていれば失効", () => {
    const r = judgeSession({ ...base, loginLinkCount: 2, loggedInIndicatorCount: 0 });
    assert.equal(r.verdict, "EXPIRED");
  });

  it("ログインリンクが出ていれば、ユーザー名が同時に取れていても失効を優先する", () => {
    // 両方出るのは想定外。安全側(再連携を促す)に倒す。
    const r = judgeSession({ ...base, loginLinkCount: 1, loggedInIndicatorCount: 1 });
    assert.equal(r.verdict, "EXPIRED");
  });

  it("ログインリンクが無くユーザー名が出ていれば有効", () => {
    assert.equal(judgeSession(base).verdict, "ACTIVE");
  });

  it("どちらも検出できなければ UNKNOWN(失効にしない)", () => {
    const r = judgeSession({ ...base, loggedInIndicatorCount: 0 });
    assert.equal(r.verdict, "UNKNOWN");
    assert.notEqual(r.verdict, "EXPIRED");
  });
});

describe("planVerifyOutcome", () => {
  it("EXPIRED のときだけ失効させる", () => {
    const plan = planVerifyOutcome({ verdict: "EXPIRED", reason: "x" });
    assert.equal(plan.markExpired, true);
    assert.equal(plan.advanceVerifiedAt, false);
  });

  it("UNKNOWN では失効させず、lastVerifiedAt も進めない", () => {
    const plan = planVerifyOutcome({ verdict: "UNKNOWN", reason: "x" });
    assert.equal(plan.markExpired, false);
    // ここを true にすると「判定できていない」ことが死活監視から消える
    assert.equal(plan.advanceVerifiedAt, false);
    assert.equal(plan.warn, true);
  });

  it("ACTIVE は lastVerifiedAt を進めるだけ", () => {
    const plan = planVerifyOutcome({ verdict: "ACTIVE", reason: "x" });
    assert.equal(plan.markExpired, false);
    assert.equal(plan.advanceVerifiedAt, true);
  });
});
