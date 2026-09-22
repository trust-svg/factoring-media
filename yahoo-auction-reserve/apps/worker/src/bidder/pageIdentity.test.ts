import assert from "node:assert/strict";
import { test } from "node:test";
import { LOGIN_HOST, NOT_FOUND_PHRASE, pageIdentityVerdict } from "./pageIdentity";

const V = (args: { url?: string; httpStatus?: number | null; bodyText?: string }) =>
  pageIdentityVerdict({
    url: args.url ?? "https://auctions.yahoo.co.jp/user/jp/show/watchlist",
    httpStatus: args.httpStatus === undefined ? 200 : args.httpStatus,
    bodyText: args.bodyText ?? "ウォッチリスト 商品1 商品2",
  });

test("普通のページは CONTENT", () => {
  const v = V({});
  assert.equal(v.kind, "CONTENT");
  assert.equal(v.reason, "");
});

test("HTTP 404 は NOT_FOUND", () => {
  const v = V({ httpStatus: 404 });
  assert.equal(v.kind, "NOT_FOUND");
  assert.match(v.reason, /404/);
});

test("本文の文言だけでも NOT_FOUND(ソフト404)", () => {
  // ⚠️ ここが効かないと 2026-08-26 の事故が再発する。
  // 200 で返る404案内ページを「中身のあるページ」として扱ってしまう
  const v = V({ httpStatus: 200, bodyText: "指定されたURLのページは存在しません。" });
  assert.equal(v.kind, "NOT_FOUND");
  assert.match(v.reason, /ソフト404/);
});

test("実際の404ページの全文で NOT_FOUND になる", () => {
  // 2026-08-26 のスクリーンショットから書き起こした本文。
  // 文言合わせのテストは実物からしか作らない
  const body = [
    "Yahoo! JAPAN ヘルプ",
    "指定されたURLのページは存在しません。",
    "Yahoo!オークションでは、お客様に楽しくお買い物をしていただくためのページをご用意しております。",
    "Yahoo!オークションならきっとみつかる！",
    "似たような商品を探す すべてのオークション 検索 条件を指定して検索",
    "カテゴリから探す",
    "コンピュータ 家電、AV、カメラ 音楽 本、雑誌 映画、ビデオ おもちゃ、ゲーム",
  ].join("\n");
  assert.equal(V({ httpStatus: 200, bodyText: body }).kind, "NOT_FOUND");
});

test("ログイン画面は LOGIN_REQUIRED", () => {
  const v = V({ url: "https://login.yahoo.co.jp/config/login?.done=..." });
  assert.equal(v.kind, "LOGIN_REQUIRED");
  assert.match(v.reason, /ログイン画面/);
});

test("ログイン判定は404判定より先(404がログイン要求に化けない)", () => {
  // 逆順だと、存在しない URL を「Cookie が失効した」と誤診して
  // セッションを EXPIRED にし、再連携を促してしまう
  const v = V({ url: `https://${LOGIN_HOST}/config/login`, httpStatus: 404 });
  assert.equal(v.kind, "LOGIN_REQUIRED");
});

test("ステータスが取れなくても本文で判定できる", () => {
  const v = V({ httpStatus: null, bodyText: `なにか ${NOT_FOUND_PHRASE} なにか` });
  assert.equal(v.kind, "NOT_FOUND");
  assert.match(v.reason, /不明/);
});

test("ステータスが取れず本文も普通なら CONTENT", () => {
  assert.equal(V({ httpStatus: null }).kind, "CONTENT");
});

test("2つの信号は独立に効く(片方が黙って効かなくなっても検知が残る)", () => {
  // ステータスだけ
  assert.equal(V({ httpStatus: 404, bodyText: "ウォッチリスト" }).kind, "NOT_FOUND");
  // 本文だけ
  assert.equal(V({ httpStatus: 200, bodyText: NOT_FOUND_PHRASE }).kind, "NOT_FOUND");
});

test("文言は実物に固定されている", () => {
  // 定数を使ったテストは文言を変えても一緒に動いて落ちない。
  // スクリーンショットで確認した実物をここで釘付けにする
  assert.equal(NOT_FOUND_PHRASE, "ページは存在しません");
  assert.equal(LOGIN_HOST, "login.yahoo.co.jp");
  assert.equal(
    V({ bodyText: "指定されたURLのページは存在しません。" }).kind,
    "NOT_FOUND",
  );
});

test("500 などの他のエラーは NOT_FOUND にしない", () => {
  // 「一時的に落ちている」と「URL が無い」は別物。
  // 一緒にすると、障害中に URL 候補を消してしまう判断につながる
  assert.equal(V({ httpStatus: 500 }).kind, "CONTENT");
  assert.equal(V({ httpStatus: 503 }).kind, "CONTENT");
});
