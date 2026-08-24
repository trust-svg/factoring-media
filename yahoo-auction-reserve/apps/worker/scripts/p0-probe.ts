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
 *   npm run p0:probe -- <商品URL> --anonymous         # 未ログインの対照(loginLink を取る)
 *   npm run p0:probe -- <商品URL> --watch 20          # 自動延長のDOM挙動(§13-3)
 *   npm run p0:probe -- <商品URL> --stage2 --amount 1200
 *   npm run p0:probe -- --watchlist                   # ウォッチリストのURL/セレクタ確定(商品URL不要)
 *   npm run p0:probe -- --watchlist --anonymous       # ログイン壁(watchlistLoginWall)の陽性対照
 *
 * 出力: tmp/p0/<auctionId>-<timestamp>.md と同名の .png (git管理外)
 */
// 最初に .env を読む(module スコープで環境変数を読むモジュールがあるため順序が重要)
import "../src/env";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { createInterface } from "node:readline/promises";
import type { BrowserContext, Locator, Page } from "playwright";
import { chromium } from "playwright";
import { prisma } from "@yar/db";
import {
  YAHOO_AUCTION_URL_PATTERN,
  decryptSecret,
  extractAuctionId,
  parseAuctionPage,
} from "@yar/shared";
import type { YahooCookie } from "@yar/shared";
import { selectors } from "../src/bidder/selectors";
import {
  WATCHLIST_URL_CANDIDATES,
  scrapeWatchlistPage,
} from "../src/jobs/watchlist";

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
    // `/jp/show/bid` は入札履歴 `/jp/show/bid_hist` にも前方一致する。
    // 除外なしの素の候補も残してあるのは、罠が当たっていることをレポート上で
    // 見えるようにするため(下の「当たった候補の実体」で別要素だと分かる)。
    "a[href*='/jp/show/bid']:not([href*='bid_hist'])",
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
  watchlistLoginWall: [
    selectors.watchlistLoginWall,
    "form[action*='login.yahoo.co.jp']",
    "input[name='login']",
    "text=ログインしてください",
  ],
  watchlistItemLink: [
    selectors.watchlistItemLink,
    "a[href*='/jp/auction/']",
    "li a[href*='auction']",
  ],
  watchlistNextPage: [
    selectors.watchlistNextPage,
    "a:has-text('次へ')",
    "a[rel='next']",
  ],
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
// ウォッチリストページで確認したいスロット(--watchlist)
const WATCHLIST_SLOTS = [
  "watchlistLoginWall",
  "watchlistItemLink",
  "watchlistNextPage",
  "loginLink",
  "loggedInIndicator",
];

interface Args {
  url: string;
  headless: boolean;
  anonymous: boolean;
  sessionRef?: string;
  watchMinutes?: number;
  stage2: boolean;
  amount?: number;
  /** ウォッチリストの URL・セレクタを確定させるモード(商品URL不要) */
  watchlist: boolean;
}

function parseArgs(argv: string[]): Args {
  const positional: string[] = [];
  const args: Args = {
    url: "",
    headless: false,
    anonymous: false,
    stage2: false,
    watchlist: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--headless") args.headless = true;
    else if (a === "--anonymous") args.anonymous = true;
    else if (a === "--stage2") args.stage2 = true;
    else if (a === "--watchlist") args.watchlist = true;
    else if (a === "--session") args.sessionRef = argv[++i];
    else if (a === "--watch") args.watchMinutes = Number(argv[++i]);
    else if (a === "--amount") args.amount = Number(argv[++i]);
    else if (a.startsWith("--")) throw new Error(`不明なオプション: ${a}`);
    else positional.push(a);
  }
  args.url = positional[0] ?? "";
  // ウォッチリストは URL 候補自体が検証対象なので、商品URLは要らない
  if (!args.url && !args.watchlist) {
    throw new Error("商品URLを渡すこと: npm run p0:probe -- <URL>");
  }
  if (args.watchlist && args.stage2) {
    throw new Error("--watchlist と --stage2 は併用できない(入札フォームには進まない)");
  }
  if (args.stage2 && !(args.amount && args.amount > 0)) {
    throw new Error("--stage2 には --amount <入札額> が必須");
  }
  if (args.stage2 && args.anonymous) {
    throw new Error("--anonymous は未ログインの対照用。--stage2 とは併用できない");
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

const trim = (s: string | null | undefined): string =>
  (s ?? "").replace(/\s+/g, " ").trim().slice(0, 50);

// 当たった候補が「どの要素」に当たったか。
// count / visible / text だけだと、別物に当たっている候補どうしを区別できない。
// 実測(2026-08-24)で `a[href*='/jp/show/bid']` が入札履歴リンクに当たり、
// 「✅ が付いているのに押すと履歴ページへ飛ぶ」状態が起きた。tag/href まで
// 出しておかないとレポートからは見抜けない。
interface NodeDesc {
  tag: string;
  id: string;
  cls: string;
  name: string;
  href: string;
  value: string;
  text: string;
}

async function describeNode(el: Locator): Promise<NodeDesc> {
  const attr = async (a: string): Promise<string> =>
    trim(await el.getAttribute(a).catch(() => ""));
  const tag = trim(
    await el.evaluate((n) => (n as { tagName?: string }).tagName ?? "").catch(() => ""),
  ).toLowerCase();
  const type = await attr("type");
  // 入力欄の value は入札額が入りうるので出さない(ボタンの value はラベルなので出す)
  const valueIsLabel = tag !== "input" || ["submit", "button", "image", "reset"].includes(type);
  return {
    tag,
    id: await attr("id"),
    cls: await attr("class"),
    name: await attr("name"),
    href: await attr("href"),
    value: valueIsLabel ? await attr("value") : "(伏せる)",
    text: trim(await el.innerText().catch(() => "")),
  };
}

// 同じ要素を指しているかの判定キー。候補どうしの突き合わせに使う
const nodeKey = (n: NodeDesc): string => [n.tag, n.id, n.href, n.text].join("|");

interface SlotResult {
  selector: string;
  count: number;
  visible: boolean;
  text: string;
  nodes: NodeDesc[];
}

// 1候補につきここまで実体を出す(類似要素が大量に当たる候補があるため)
const NODES_PER_CANDIDATE = 3;

// 候補セレクタの総当り。hit の一覧を返す
async function probeSlot(page: Page, slot: string): Promise<SlotResult[]> {
  const results: SlotResult[] = [];
  for (const selector of CANDIDATES[slot] ?? []) {
    try {
      const loc = page.locator(selector);
      const count = await loc.count();
      if (count === 0) {
        results.push({ selector, count: 0, visible: false, text: "", nodes: [] });
        continue;
      }
      const first = loc.first();
      const visible = await first.isVisible().catch(() => false);
      const nodes: NodeDesc[] = [];
      for (let i = 0; i < Math.min(count, NODES_PER_CANDIDATE); i++) {
        nodes.push(await describeNode(loc.nth(i)));
      }
      results.push({ selector, count, visible, text: nodes[0]?.text ?? "", nodes });
    } catch (err) {
      // セレクタ構文自体が通らない場合もここに来る
      results.push({
        selector,
        count: -1,
        visible: false,
        text: err instanceof Error ? err.message.slice(0, 60) : String(err),
        nodes: [],
      });
    }
  }
  return results;
}

async function reportSlots(page: Page, slots: string[]): Promise<void> {
  for (const slot of slots) {
    const results = await probeSlot(page, slot);
    const hits = results.filter((r) => r.count > 0 && r.visible);
    // 当たった候補が別々の要素を指しているなら、先頭を採るのは単なる運試し。
    // ここで見出しに ✅ を出さないのは、✅ が「そのまま selectors.ts に写してよい」
    // という意味に読まれるため。
    const distinct = new Set(
      hits.map((h) => (h.nodes[0] ? nodeKey(h.nodes[0]) : `?${h.selector}`)),
    );
    const head =
      hits.length === 0
        ? "❌ 全滅"
        : distinct.size === 1
          ? "✅ " + hits[0].selector
          : `⚠️ ${hits.length}件が当たったが指す要素が ${distinct.size} 種類ある`;
    say(`### ${slot} ${head}`);
    say("");
    say("| 候補 | 件数 | 可視 | テキスト |");
    say("|---|---|---|---|");
    for (const r of results) {
      const n = r.count < 0 ? "err" : String(r.count);
      say(`| \`${r.selector}\` | ${n} | ${r.visible ? "○" : "-"} | ${r.text} |`);
    }
    say("");
    if (hits.length > 0) {
      say("**当たった候補の実体**");
      say("");
      say("| 候補 | # | tag | id | class | name | text/value | href |");
      say("|---|---|---|---|---|---|---|---|");
      for (const h of hits) {
        h.nodes.forEach((n, i) => {
          say(
            `| \`${h.selector}\` | ${i + 1}/${h.count} | ${n.tag} | ${n.id} | ${n.cls} | ${n.name} | ${n.text || n.value} | ${n.href} |`,
          );
        });
      }
      say("");
    }
    if (distinct.size > 1) {
      say(
        "> ⚠️ 当たった候補が **別々の要素** を指している。どれか(あるいは全部)が罠。" +
          "実体の tag / href を見て、本当に押したい要素を指す候補だけを selectors.ts に写すこと。",
      );
      say("");
    }
  }
}

// 候補が全滅したときに実物の構造を知るためのダンプ。
// これが無いと「全部 ❌」だけ分かって次の一手が出ない。
//
// page.evaluate を使えば1往復で済むが、それをやると worker の tsconfig に DOM の
// 型を入れることになり、Node 側のコードでも document 等が書けてしまう。
// プローブは実行回数が少ないので、往復が増えても locator API だけで組む。
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
  // limit は「拾えた件数」に掛ける。走査位置に掛けると、visibleOnly のときに
  // 不可視要素が枠を食い潰し、目当ての要素まで届かないまま打ち切られる。
  for (let i = 0; i < total && rows.length < limit; i++) {
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

  // `a[href*='auction']` だと 類似商品・出品者の他の商品 のリンクが数十件並び、
  // 入札エリアに届く前に件数上限を使い切る(2026-08-24 の実測でそうなった)。
  // 商品詳細リンク(/jp/auction/<id>)は除き、操作系の /jp/show/ 配下だけ拾う。
  const clickable = await dumpElements(
    page,
    "button, input[type=submit], input[type=button], a[href*='bid'], a[href*='/jp/show/']",
    ["id", "class", "name", "href", "value"],
    100,
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

/**
 * ウォッチリストの URL 候補とセレクタを確定させる(--watchlist)。
 *
 * 目的は3つ:
 *   1. WATCHLIST_URL_CANDIDATES のどれが生きているか
 *   2. watchlistLoginWall / watchlistItemLink / watchlistNextPage の当たり
 *   3. 本番と同じ `scrapeWatchlistPage` が何を返すか
 *
 * 3 を必ず通すのは、プローブ用の別ロジックで「当たった」と判断すると、
 * 本番コードだけが外れたままでも気づけないため。
 * `--anonymous` で回すとログイン壁の陽性対照が取れる。
 */
async function probeWatchlist(
  page: Page,
  reportPath: string,
  anonymous: boolean,
): Promise<void> {
  for (const [idx, url] of WATCHLIST_URL_CANDIDATES.entries()) {
    say(`## 候補URL ${idx + 1}: ${url}`);
    say("");

    const t0 = Date.now();
    try {
      await page.goto(url, { waitUntil: "domcontentloaded" });
    } catch (err) {
      say(`- ⚠️ 遷移に失敗: ${err instanceof Error ? err.message : String(err)}`);
      say("");
      continue;
    }
    say(`- 到達URL: ${page.url()}`);
    say(`- ページタイトル: ${await page.title()}`);
    say(`- 所要: ${Date.now() - t0}ms`);
    if (/login\.yahoo\.co\.jp/.test(page.url())) {
      say(
        anonymous
          ? "- ✅ 未ログインでログイン画面へ飛んだ(= ログイン必須の陽性対照)"
          : "- ⚠️ **ログイン画面へリダイレクトされた = Cookie が失効している**",
      );
    }
    say("");

    await reportSlots(page, WATCHLIST_SLOTS);

    // セレクタに依存しない実数。watchlistItemLink が外れていても
    // 「このページに商品リンクが何件あるか」はこれで分かる。
    const rawHrefs = await page
      .locator("a[href]")
      .evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? ""));
    const pageUrl = page.url();
    const ids = new Set<string>();
    for (const h of rawHrefs) {
      if (!h) continue;
      let abs = "";
      try {
        abs = new URL(h, pageUrl).toString();
      } catch {
        continue;
      }
      const m = YAHOO_AUCTION_URL_PATTERN.exec(abs);
      if (m?.[1]) ids.add(m[1]);
    }
    say(`- ページ内の商品ID付きリンク(重複除く): **${ids.size}件**`);
    say(`  - 例: ${[...ids].slice(0, 5).join(", ") || "(0件)"}`);
    say("");

    // 本番コードをそのまま通す。ここの kind がプローブの結論。
    const result = await scrapeWatchlistPage(page);
    say(
      `- \`scrapeWatchlistPage\` の判定: **${result.kind}** / ${result.itemCount}件` +
        (result.detail ? ` (${result.detail})` : ""),
    );
    if (result.kind === "UNPARSEABLE" && ids.size > 0) {
      say(
        "  - ⚠️ 商品リンクは存在するのに本番コードは0件。**watchlistItemLink が外れている**",
      );
    }
    say("");

    await discovery(page);

    const shot = reportPath.replace(/\.md$/, `-wl${idx + 1}.png`);
    await page.screenshot({ path: shot, fullPage: false }).catch(() => {});
  }

  say("### 次にやること");
  say("");
  say("- `scrapeWatchlistPage` が OK を返した候補URLを WATCHLIST_URL_CANDIDATES の先頭にする");
  say("- 当たったセレクタを selectors.ts に書き、状態表を ✅ に更新する");
  say("- `--anonymous` の回で watchlistLoginWall が当たっていることを確認する(陰陽の対照)");
  say("");
}

// 認証済み DOM に対してパーサが機能するかを見る(未認証 fetch とは差が出うる)
async function reportParser(page: Page, url: string, anonymous: boolean): Promise<void> {
  const info = parseAuctionPage(await page.content(), url);
  say(`### パーサ結果(${anonymous ? "未ログイン" : "認証済み"} DOM)`);
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

async function launchContext(headless: boolean): Promise<BrowserContext> {
  const browser = await chromium.launch({
    headless,
    executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
  });
  return browser.newContext({
    locale: "ja-JP",
    timezoneId: JST,
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
  });
}

// --anonymous: Cookie を一切載せない対照実行。
// ログイン中のページからは loginLink のセレクタが取れないうえ、
// loggedInIndicator が本当にログイン状態を追っているか(ログアウト時に消えるか)を
// 確かめる手段が無い。この2つはここでしか取れない。
async function anonymousContext(
  headless: boolean,
): Promise<{ context: BrowserContext; close: () => Promise<void> }> {
  say("### 未ログイン(--anonymous / Cookie なし)");
  say("");
  say("> 連携 Cookie は読み込んでいない。loginLink の確定と、loggedInIndicator の");
  say("> 陰性対照(ログアウト状態では当たらないこと)を取るための実行。");
  say("");
  const context = await launchContext(headless);
  return { context, close: () => context.browser()?.close() ?? Promise.resolve() };
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

  const context = await launchContext(headless);
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
  return { context, close: () => context.browser()?.close() ?? Promise.resolve() };
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
  const slug = args.watchlist ? "watchlist" : auctionId;
  const reportPath = resolve(
    process.cwd(),
    `../../tmp/p0/${slug}${args.anonymous ? "-anon" : ""}-${stamp}.md`,
  );
  mkdirSync(dirname(reportPath), { recursive: true });

  say(`# P0 プローブ結果 — ${slug}`);
  say("");
  say(`- 実行(JST): ${fmt(new Date())}`);
  say(`- URL: ${args.url || "(ウォッチリストモード: 候補URLを順に試す)"}`);
  say(`- headless: ${args.headless}`);
  say(`- 認証: ${args.anonymous ? "**未ログイン(Cookie なし)**" : "連携 Cookie あり"}`);
  say(
    `- stage: ${
      args.watchlist
        ? "watchlist (ウォッチリストのURL・セレクタ確定)"
        : args.stage2
          ? "2 (入札フォーム〜確認画面)"
          : "1 (読むだけ)"
    }`,
  );
  say("");

  const { context, close } = args.anonymous
    ? await anonymousContext(args.headless)
    : await resolveContext(args.headless, args.sessionRef);
  const page = await context.newPage();

  if (args.watchlist) {
    await probeWatchlist(page, reportPath, args.anonymous);
    writeFileSync(reportPath, out.join("\n"), "utf-8");
    console.log(`\nレポート: ${reportPath}`);
    await close();
    await prisma.$disconnect();
    return;
  }

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
  await reportParser(page, args.url, args.anonymous);
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
