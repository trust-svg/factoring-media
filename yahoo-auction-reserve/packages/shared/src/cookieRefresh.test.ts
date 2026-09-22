import assert from "node:assert/strict";
import test from "node:test";
import type { YahooCookie } from "./types";
import { planCookieRefresh, toYahooCookies } from "./cookieRefresh";

const C = (name: string, value: string, extra: Partial<YahooCookie> = {}): YahooCookie => ({
  name,
  value,
  domain: ".yahoo.co.jp",
  path: "/",
  secure: true,
  ...extra,
});

/** 保管済みの最低限そろった一式(T / Y / SSL) */
const stored: YahooCookie[] = [C("T", "t-old"), C("Y", "y-old"), C("SSL", "ssl-old")];

test("値が更新されていれば保存する", () => {
  const fresh = [C("T", "t-new"), C("Y", "y-old"), C("SSL", "ssl-old")];
  const plan = planCookieRefresh(stored, fresh);
  assert.equal(plan.save, true);
  assert.deepEqual(plan.save ? plan.cookies : null, fresh);
});

test("有効期限だけが延びた場合も保存する", () => {
  const fresh = [
    C("T", "t-old", { expires: 1800000000 }),
    C("Y", "y-old"),
    C("SSL", "ssl-old"),
  ];
  const plan = planCookieRefresh(stored, fresh);
  assert.equal(plan.save, true);
});

test("中身が同じなら保存しない", () => {
  const plan = planCookieRefresh(stored, [C("T", "t-old"), C("Y", "y-old"), C("SSL", "ssl-old")]);
  assert.equal(plan.save, false);
});

test("並び順が違うだけなら保存しない", () => {
  const plan = planCookieRefresh(stored, [C("SSL", "ssl-old"), C("T", "t-old"), C("Y", "y-old")]);
  assert.equal(plan.save, false);
});

test("保管済みにあった認証 Cookie が消えていたら保存しない", () => {
  // ログアウト・取得失敗で良いスナップショットを潰さない(fail-closed)
  const plan = planCookieRefresh(stored, [C("T", "t-new"), C("Y", "y-new")]);
  assert.equal(plan.save, false);
  assert.match(plan.save ? "" : plan.reason, /SSL/);
});

test("認証 Cookie が空文字になっていたら消えたものとして保存しない", () => {
  const plan = planCookieRefresh(stored, [C("T", "t-new"), C("Y", "y-new"), C("SSL", "")]);
  assert.equal(plan.save, false);
  assert.match(plan.save ? "" : plan.reason, /SSL/);
});

test("空の一式では保存しない", () => {
  const plan = planCookieRefresh(stored, []);
  assert.equal(plan.save, false);
});

test("yahoo.co.jp 以外のドメインは保存しない", () => {
  const fresh = [
    C("T", "t-new"),
    C("Y", "y-old"),
    C("SSL", "ssl-old"),
    C("ad", "x", { domain: ".doubleclick.net" }),
  ];
  const plan = planCookieRefresh(stored, fresh);
  assert.equal(plan.save, true);
  const names = (plan.save ? plan.cookies : []).map((c) => c.name);
  assert.deepEqual(names.includes("ad"), false);
});

test("保管済みに無かった認証 Cookie は欠けていても保存を止めない", () => {
  // stored に SSL が無い連携なら、fresh に SSL が無くても「消えた」ではない
  const storedNoSsl = [C("T", "t-old"), C("Y", "y-old")];
  const plan = planCookieRefresh(storedNoSsl, [C("T", "t-new"), C("Y", "y-old")]);
  assert.equal(plan.save, true);
});

test("認証以外の Cookie が減っただけなら保存する", () => {
  const storedWithExtra = [...stored, C("irepIsLogin", "1")];
  const plan = planCookieRefresh(storedWithExtra, [C("T", "t-old"), C("Y", "y-old"), C("SSL", "ssl-old")]);
  assert.equal(plan.save, true);
});

// --- Playwright の返す形からの変換 ---

test("セッション Cookie の expires -1 は落とす(保管形式と揃える)", () => {
  // ⚠️ 落とさないと、登録時(expires 無し)と毎回差分が出て
  //    「変化なし」の判定が永久に効かなくなる
  const v = toYahooCookies([
    { name: "T", value: "t", domain: ".yahoo.co.jp", path: "/", expires: -1, httpOnly: true, secure: true, sameSite: "Lax" },
  ]);
  assert.equal("expires" in v[0]!, false);
});

test("有効期限つきはそのまま残す", () => {
  const v = toYahooCookies([
    { name: "T", value: "t", domain: ".yahoo.co.jp", path: "/", expires: 1800000000.5, httpOnly: true, secure: true, sameSite: "Lax" },
  ]);
  assert.equal(v[0]!.expires, 1800000000);
});

test("Playwright の sameSite 以外の値は付けない", () => {
  const v = toYahooCookies([
    { name: "T", value: "t", domain: ".yahoo.co.jp", path: "/", expires: -1, httpOnly: true, secure: true, sameSite: "None" as never },
  ]);
  assert.equal(v[0]!.sameSite, "None");
});

test("変換した一式は同じ内容なら保存不要と判定される", () => {
  const plan = planCookieRefresh(
    stored,
    toYahooCookies([
      { name: "T", value: "t-old", domain: ".yahoo.co.jp", path: "/", expires: -1, httpOnly: false, secure: true },
      { name: "Y", value: "y-old", domain: ".yahoo.co.jp", path: "/", expires: -1, httpOnly: false, secure: true },
      { name: "SSL", value: "ssl-old", domain: ".yahoo.co.jp", path: "/", expires: -1, httpOnly: false, secure: true },
    ]),
  );
  assert.equal(plan.save, false);
});
