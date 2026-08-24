/**
 * =============================================================
 * P0 検証プローブ (設計 §13)
 * =============================================================
 * selectors.ts のセレクタは全て未検証のプレースホルダなので、実ページの
 * DOM を人手で読んで埋める必要がある。このスクリプトはその作業を
 * 「候補セレクタの総当り + 周辺 DOM のダンプ」に落として一発で済ませるための道具。
 *
 * 実行するのは人間(設計の指示)。CI や worker からは絶対に呼ばないこと。
 *
 * Stage 1 (既定): 商品ページを開いて読むだけ。クリック・入力は一切しない。
 * Stage 2 (--stage2): 入札フォーム〜確認画面まで進む。
 *          **最終確定ボタンは絶対に押さない**(押すのは人間が画面上で手動)。
 *
 * 使い方:
 *   npm run p0:probe -- <商品URL>
 *   npm run p0:probe -- <商品URL> --headless          # bot検知の比較用(§13-4)
 *   npm run p0:probe -- <商品URL> --watch 20          # 自動延長のDOM挙動(§13-3)
 *   npm run p0:probe -- <商品URL> --stage2 --amount 1200
 *
 * 出力: tmp/p0/<auctionId>-<timestamp>.md と同名の .png (git管理外)
 */
// 最初に .env を読む(module スコープで環境変数を読むモジュールがあるため順序が重要)
import "../src/env";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { createInterface } from "node:readline/promises";
import type { BrowserContext, Page } from "playwright";
import { chromium } from "playwright";
import { prisma } from "@yar/db";
import { decryptSecret, extractAuctionId, parseAuctionPage } from "@yar/shared";
import type { YahooCookie } from "@yar/shared";
import { selectors } from "../src/bidder/selectors";

// ---------------------------------------------------------------
// 候補セレクタ
//
// ここに並んでいるものは **全て仮説**。selectors.ts の現行値(=プレースホルダ)に
// 加えて、テキストベースなど壊れにくい書き方の候補を混ぜてある。
// プローブの目的は「どれが当たったか」を知ることであって、当たり前提で使うことではない。
// 全滅したときのために discovery ダンプ(後述)を必ず併せて見ること。
// ---------------------------------------------------------------
const CANDIDATES: Record<string, string[]> = {
  loggedInIndicator: [
    selectors.loggedInIndicator,
    "#msthdBs",
    "header a[href*='profile.yahoo.co.jp']",
    "text=ログアウト",
  ],
  loginLink: [
    selectors.loginLink,
    "a[href*='login.yahoo.co.jp']",
    "text=ログイン",
  ],
  bidButton: [
    selectors.bidButton,
    "#bid",
    "a[href*='/jp/show/bid']",
    "form[name='bidform'] input[type='submit']",
    "text=入札する",
  ],
  priceInput: [
    selectors.priceInput,
    "input[name='Bid_price']",
    "input[name='bidYen']",
    "input[name='price']",
    "input[type='tel'][name*='price' i]",
  ],
  bidConfirmButton: [
    selectors.bidConfirmButton,
    "input[type='submit'][value*='確認']",
    "button:has-text('確認')",
    "text=入札内容を確認",
  ],
  bidSubmitButton: [
    selectors.bidSubmitButton,
    "input[type='submit'][value*='入札']",
    "button:has-text('入札する')",
  ],
  wonIndicator: [selectors.wonIndicator, "text=落札しました"],
  highestBidderIndicator: [
    selectors.highestBidderIndicator,
    "text=最高額入札者",
  ],
  outbidIndicator: [selectors.outbidIndicator, "text=高値更新"],
};

// 商品ページで確認したいスロット(Stage 1 で見る)
const STAGE1_SLOTS = [
  "loggedInIndicator",
  "loginLink",
  "bidButton",
  "wonIndicator",
  "highestBidderIndicator",
  "outbidIndicator",
];
// 入札フォーム〜確認画面で確認したいスロット(Stage 2 で見る)
const STAGE2_SLOTS = ["priceInput", "bidConfirmButton", "bidSubmitButton"];

interface Args {
  url: string;
  headless: boolean;
  sessionRef?: string;
  watchMinutes?: number;
  stage2: boolean;
  amount?: number;
}

function parseArgs(argv: string[]): Args {
  const positional: string[] = [];
  const args: Args = { url: "", headless: false, stage2: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--headless") args.headless = true;
    else if (a === "--stage2") args.stage2 = true;
    else if (a === "--session") args.sessionRef = argv[++i];
    else if (a === "--watch") args.watchMinutes = Number(argv[++i]);
    else if (a === "--amount") args.amount = Number(argv[++i]);
    else if (a.startsWith("--")) throw new Error(`不明なオプション: ${a}`);
    else positional.push(a);
  }
  args.url = positional[0] ?? "";
  if (!args.url) throw new Error("商品URLを渡すこと: npm run p0:probe -- <URL>");
  if (args.stage2 && !(args.amount && args.amount > 0)) {
    throw new Error("--stage2 には --amount <入札額> が必須");
  }
  return args;
}

const JST = "Asia/Tokyo";
const fmt = (d: Date | undefined) =>
  d ? d.toLocaleString("ja-JP", { timeZone: JST }) : "(取得できず)";

const out: string[] = [];
function say(line = ""): void {
  console.log(line);
  out.push(line);
}

// 候補セレクタの総当り。hit の一覧を返す
async function probeSlot(
  page: Page,
  slot: string,
): Promise<{ selector: string; count: number; visible: boolean; text: string }[]> {
  const results = [];
  for (const selector of CANDIDATES[slot] ?? []) {
    try {
      const loc = page.locator(selector);
      const count = await loc.count();
      if (count === 0) {
        results.push({ selector, count: 0, visible: false, text: "" });
        continue;
      }
      const first = loc.first();
      const visible = await first.isVisible().catch(() => false);
      const text = ((await first.innerText().catch(() => "")) || "")
        .replace(/\s+/g, " ")
        .slice(0, 60);
      results.push({ selector, count, visible, text });
    } catch (err) {
      // セレクタ構文自体が通らない場合もここに来る
      results.push({
        selector,
        count: -1,
        visible: false,
        text: err instanceof Error ? err.message.slice(0, 60) : String(err),
      });
    }
  }
  return results;
}

async function reportSlots(page: Page, slots: string[]): Promise<void> {
  for (const slot of slots) {
    const results = await probeSlot(page, slot);
    const hit = results.find((r) => r.count > 0 && r.visible);
    say(`### ${slot} ${hit ? "✅ " + hit.selector : "❌ 全滅"}`);
    say("");
    say("| 候補 | 件数 | 可視 | テキスト |");
    say("|---|---|---|---|");
    for (const r of results) {
      const n = r.count < 0 ? "err" : String(r.count);
      say(`| \`${r.selector}\` | ${n} | ${r.visible ? "○" : "-"} | ${r.text} |`);
    }
    say("");
  }
}

// 候補が全滅したときに実物の構造を知るためのダンプ。
// これが無いと「全部 ❌」だけ分かって次の一手が出ない。
//
// page.evaluate を使えば1往復で済むが、それをやると worker の tsconfig に DOM の
// 型を入れることになり、Node 側のコードでも document 等が書けてしまう。
// プローブは実行回数が少ないので、往復が増えても locator API だけで組む。
const trim = (s: string | null | undefined): string =>
  (s ?? "").replace(/\s+/g, " ").trim().slice(0, 50);

async function dumpElements(
  page: Page,
  selector: string,
  attrs: string[],
  limit: number,
  visibleOnly: boolean,
): Promise<Record<string, string>[]> {
  const loc = page.locator(selector);
  const total = await loc.count();
  const rows: Record<string, string>[] = [];
  for (let i = 0; i < Math.min(total, limit); i++) {
    const el = loc.nth(i);
    if (visibleOnly && !(await el.isVisible().catch(() => false))) continue;
    const row: Record<string, string> = {};
    for (const a of attrs) row[a] = trim(await el.getAttribute(a).catch(() => ""));
    row.tag = trim(
      await el.evaluate((n) => (n as { tagName?: string }).tagName ?? "").catch(() => ""),
    ).toLowerCase();
    row.text = trim(await el.innerText().catch(() => ""));
    rows.push(row);
  }
  return rows;
}

async function discovery(page: Page): Promise<void> {
  say("### 実物ダンプ(候補が全滅したときはここから拾う)");
  say("");

  const clickable = await dumpElements(
    page,
    "button, input[type=submit], input[type=button], a[href*='bid'], a[href*='auction']",
    ["id", "class", "name", "href", "value"],
    60,
    true,
  );
  say("**可視のクリック要素**");
  say("");
  say("| tag | id | class | name | text/value | href |");
  say("|---|---|---|---|---|---|");
  for (const c of clickable) {
    say(
      `| ${c.tag} | ${c.id} | ${c.class} | ${c.name} | ${c.text || c.value} | ${c.href} |`,
    );
  }
  say("");

  // value は入力済みの入札額が入りうるので取得しない
  const inputs = await dumpElements(page, "input", ["type", "name", "id"], 60, false);
  say("**input 一覧(value は出さない)**");
  say("");
  say("| type | name | id |");
  say("|---|---|---|");
  for (const i of inputs) say(`| ${i.type} | ${i.name} | ${i.id} |`);
  say("");

  const testids = await dumpElements(page, "[data-testid]", ["data-testid"], 60, false);
  const ids = testids.map((t) => t["data-testid"]).filter(Boolean);
  say(`**data-testid**: ${ids.join(", ") || "(1つも無い)"}`);
  say("");
}

// 認証済み DOM に対してパーサが機能するかを見る(未認証 fetch とは差が出うる)
async function reportParser(page: Page, url: string): Promise<void> {
  const info = parseAuctionPage(await page.content(), url);
  say("### パーサ結果(認証済み DOM)");
  say("");
  say("| 項目 | 値 |");
  say("|---|---|");
  say(`| title | ${info.title ?? "(取得できず)"} |`);
  say(`| currentPrice | ${info.currentPrice ?? "(取得できず)"} |`);
  say(`| endAt (JST) | ${fmt(info.endAt)} |`);
  say(`| hasAutoExtension | ${info.hasAutoExtension ?? "(取得できず)"} |`);
  say(`| sellerName | ${info.sellerName ?? "(取得できず)"} |`);
  say(`| isClosed | ${info.isClosed ?? "(取得できず)"} |`);
  say("");
  if (info.endAt === undefined || info.currentPrice === undefined) {
    say("> ⚠️ 終了時刻か現在価格が取れていない。ここが取れないと監視ジョブが機能しない。");
    say("");
  }
}

async function resolveContext(
  headless: boolean,
  sessionRef?: string,
): Promise<{ context: BrowserContext; close: () => Promise<void> }> {
  const sessions = await prisma.yahooSession.findMany({
    select: { id: true, label: true, status: true, createdAt: true },
    orderBy: { createdAt: "desc" },
  });
  if (sessions.length === 0) {
    throw new Error("YahooSession が1件も無い。先に /settings/yahoo で Cookie を登録すること");
  }
  const target = sessionRef
    ? sessions.find((s) => s.id === sessionRef || s.label === sessionRef)
    : sessions[0];
  if (!target) {
    throw new Error(
      `session が見つからない: ${sessionRef}\n候補:\n` +
        sessions.map((s) => `  ${s.id}  ${s.label}  (${s.status})`).join("\n"),
    );
  }
  if (sessions.length > 1 && !sessionRef) {
    say(`> 連携が ${sessions.length} 件ある。最新の「${target.label}」を使う(--session で指定可)`);
    say("");
  }

  const row = await prisma.yahooSession.findUniqueOrThrow({ where: { id: target.id } });
  const cookies = JSON.parse(decryptSecret(row.encryptedCookie)) as YahooCookie[];

  // §13-1 の実測用。値は絶対に出さない。名前と失効時刻だけ。
  say(`### 使用する連携: ${target.label} (${target.status})`);
  say("");
  say("| Cookie名 | 失効(JST) |");
  say("|---|---|");
  for (const c of cookies) {
    const exp =
      c.expires && c.expires > 0 ? fmt(new Date(c.expires * 1000)) : "セッション限り";
    say(`| ${c.name} | ${exp} |`);
  }
  say("");

  const browser = await chromium.launch({
    headless,
    executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  const context = await browser.newContext({
    locale: "ja-JP",
    timezoneId: JST,
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
  });
  await context.addCookies(
    cookies.map((c) => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path ?? "/",
      expires: c.expires,
      httpOnly: c.httpOnly,
      secure: c.secure ?? true,
      sameSite: c.sameSite,
    })),
  );
  return { context, close: () => browser.close() };
}

// §13-3: 終了間際に張り付いて、終了時刻・価格の変化を観測する
async function watchExtension(page: Page, url: string, minutes: number): Promise<void> {
  const until = Date.now() + minutes * 60_000;
  let prevEnd = "";
  let prevPrice = "";
  say(`### 自動延長の観測(${minutes}分・15秒ごと)`);
  say("");
  say("| 時刻(JST) | endAt | currentPrice | 変化 |");
  say("|---|---|---|---|");
  while (Date.now() < until) {
    await page.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
    const info = parseAuctionPage(await page.content(), url);
    const end = fmt(info.endAt);
    const price = String(info.currentPrice ?? "-");
    const changed = [
      prevEnd && end !== prevEnd ? "⏰終了時刻が動いた" : "",
      prevPrice && price !== prevPrice ? "💴価格が動いた" : "",
    ]
      .filter(Boolean)
      .join(" / ");
    say(`| ${fmt(new Date())} | ${end} | ${price} | ${changed} |`);
    prevEnd = end;
    prevPrice = price;
    if (info.isClosed) {
      say("");
      say("> 終了を検知したので観測を打ち切る。");
      break;
    }
    await page.waitForTimeout(15_000);
  }
  say("");
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const auctionId = extractAuctionId(args.url) ?? "unknown";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const reportPath = resolve(
    process.cwd(),
    `../../tmp/p0/${auctionId}-${stamp}.md`,
  );
  mkdirSync(dirname(reportPath), { recursive: true });

  say(`# P0 プローブ結果 — ${auctionId}`);
  say("");
  say(`- 実行(JST): ${fmt(new Date())}`);
  say(`- URL: ${args.url}`);
  say(`- headless: ${args.headless}`);
  say(`- stage: ${args.stage2 ? "2 (入札フォーム〜確認画面)" : "1 (読むだけ)"}`);
  say("");

  const { context, close } = await resolveContext(args.headless, args.sessionRef);
  const page = await context.newPage();

  const t0 = Date.now();
  await page.goto(args.url, { waitUntil: "domcontentloaded" });
  say(`### 遷移`);
  say("");
  say(`- 到達URL: ${page.url()}`);
  say(`- ページタイトル: ${await page.title()}`);
  say(`- 所要: ${Date.now() - t0}ms`);
  if (/login\.yahoo\.co\.jp/.test(page.url())) {
    say("- ⚠️ **ログイン画面へリダイレクトされた = Cookie が失効している**");
  }
  say("");

  await reportSlots(page, STAGE1_SLOTS);
  await reportParser(page, args.url);
  await discovery(page);

  const shot1 = reportPath.replace(/\.md$/, "-stage1.png");
  await page.screenshot({ path: shot1 }).catch(() => {});

  if (args.watchMinutes && args.watchMinutes > 0) {
    await watchExtension(page, args.url, args.watchMinutes);
  }

  if (args.stage2) {
    say("## Stage 2 — 入札フォーム〜確認画面");
    say("");
    say("> **このスクリプトは確定ボタンを押さない。**");
    say("> 確認画面まで進めたらブラウザを開いたまま止めるので、確定するかどうかは人が決める。");
    say("");
    const steps: { name: string; ms: number; ok: boolean; detail: string }[] = [];
    const step = async (name: string, fn: () => Promise<void>) => {
      const s = Date.now();
      try {
        await fn();
        steps.push({ name, ms: Date.now() - s, ok: true, detail: "" });
        return true;
      } catch (err) {
        steps.push({
          name,
          ms: Date.now() - s,
          ok: false,
          detail: err instanceof Error ? err.message.split("\n")[0] : String(err),
        });
        return false;
      }
    };

    // 入札ボタン: Stage 1 で当たった候補を使う
    const bidHits = (await probeSlot(page, "bidButton")).filter(
      (r) => r.count > 0 && r.visible,
    );
    if (bidHits.length === 0) {
      say("入札ボタンの候補が全滅しているため Stage 2 は進めない。上のダンプから候補を足すこと。");
    } else {
      const bidSel = bidHits[0].selector;
      say(`使用した入札ボタン: \`${bidSel}\``);
      say("");
      const ok = await step("入札ボタンをクリック", async () => {
        await page.locator(bidSel).first().click({ timeout: 15_000 });
        await page.waitForLoadState("domcontentloaded", { timeout: 15_000 });
      });
      if (ok) {
        await reportSlots(page, STAGE2_SLOTS);
        await discovery(page);
        const priceHits = (await probeSlot(page, "priceInput")).filter((r) => r.count > 0);
        if (priceHits.length > 0) {
          await step(`入札額 ${args.amount} を入力`, async () => {
            await page.locator(priceHits[0].selector).first().fill(String(args.amount), {
              timeout: 15_000,
            });
          });
        }
        const confirmHits = (await probeSlot(page, "bidConfirmButton")).filter(
          (r) => r.count > 0 && r.visible,
        );
        if (confirmHits.length > 0) {
          await step("確認画面へ進む", async () => {
            await page.locator(confirmHits[0].selector).first().click({ timeout: 15_000 });
            await page.waitForLoadState("domcontentloaded", { timeout: 15_000 });
          });
          say("### 確認画面のスロット");
          say("");
          await reportSlots(page, ["bidSubmitButton"]);
          await discovery(page);
        }
      }

      say("### ステップ所要時間(§13-2 の実測値。デフォルト秒数の根拠にする)");
      say("");
      say("| ステップ | 所要 | 結果 |");
      say("|---|---|---|");
      for (const s of steps) {
        say(`| ${s.name} | ${s.ms}ms | ${s.ok ? "○" : "× " + s.detail} |`);
      }
      say(`| **合計** | **${steps.reduce((a, b) => a + b.ms, 0)}ms** | |`);
      say("");
    }

    const shot2 = reportPath.replace(/\.md$/, "-stage2.png");
    await page.screenshot({ path: shot2 }).catch(() => {});

    if (!args.headless) {
      console.log(
        "\n>>> 確認画面で止めた。確定するなら画面上で自分でクリックすること。\n>>> 終わったら Enter を押すとブラウザを閉じる。",
      );
      const rl = createInterface({ input: process.stdin, output: process.stdout });
      await rl.question("");
      rl.close();
    }
  }

  writeFileSync(reportPath, out.join("\n"), "utf-8");
  console.log(`\nレポート: ${reportPath}`);

  await close();
  await prisma.$disconnect();
}

main().catch(async (err) => {
  console.error("[p0-probe]", err instanceof Error ? err.message : err);
  await prisma.$disconnect().catch(() => {});
  process.exit(1);
});
