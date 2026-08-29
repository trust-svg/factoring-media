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
 * Stage 3 (--stage3): **実際に入札する。取り消せない。**
 *          worker が本番で使う placeBid() をそのまま呼び、押した後に
 *          商品ページを開き直して「最高額入札者になっているか」を読み戻す。
 *          クリックできたこと(SUCCESS)を成功の根拠にしない。
 *
 * ⚠️ Stage 2 と Stage 3 の関係: 先に Stage 2 で確定ボタンのヒット数を測ること。
 *    1件でないなら Stage 3 を回してはいけない(押す対象が一意に決まっていない)。
 *
 * 使い方:
 *   npm run p0:probe -- <商品URL>
 *   npm run p0:probe -- <商品URL> --headless          # bot検知の比較用(§13-4)
 *   npm run p0:probe -- <商品URL> --anonymous         # 未ログインの対照(loginLink を取る)
 *   npm run p0:probe -- <商品URL> --watch 20          # 自動延長のDOM挙動(§13-3)
 *   npm run p0:probe -- <商品URL> --stage2 --amount 1200
 *   npm run p0:probe -- <商品URL> --stage3 --amount 1   # ★実入札(要タイプ確認)
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
  minimumBidToBeat,
  parseAuctionPage,
} from "@yar/shared";
import type { YahooCookie } from "@yar/shared";
import { selectors } from "../src/bidder/selectors";
import { placeBid } from "../src/bidder/placeBid";
import { confirmClickVerdict } from "../src/bidder/probeSafety";
import { bidLandingVerdict, listStabilityVerdict } from "../src/bidder/pageReady";
import { settlePage } from "../src/bidder/settle";
import {
  CAROUSEL_ANCESTOR_SELECTOR,
  watchlistScopeVerdict,
} from "../src/bidder/watchlistScope";
import { pageIdentityVerdict } from "../src/bidder/pageIdentity";
import { redactUrl } from "../src/bidder/urlSafe";
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
//
// ⚠️ `{ sel, trap }` 形式の候補は **罠と分かっている候補**。
// 2026-08-25 の実測で、ゆるい候補がフッターや入札履歴を掴んだまま
// 「✅」として報告され、Stage 2 がそれを押した(入札履歴ページが開いた)。
// 罠候補は「当たること自体が情報」なので消さずに残すが、
//   - 見出しの ✅ には数えない
//   - Stage 2 のクリック対象には選ばない
// ようにして、レポートを読む人が取り違えないようにする。
// ---------------------------------------------------------------
interface TrapCandidate {
  sel: string;
  /** なぜ罠なのか。レポートにそのまま出る */
  trap: string;
}
type Candidate = string | TrapCandidate;

const CANDIDATES: Record<string, Candidate[]> = {
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
    "a[href*='/jp/show/bid']:not([href*='bid_hist'])",
    {
      sel: "a[href*='/jp/show/bid']",
      // 2026-08-25 に実際に押してしまった候補。入札履歴 `/jp/show/bid_hist`
      // に前方一致するので、「5件」という履歴リンクを掴んで開いた
      trap: "入札履歴 /jp/show/bid_hist に前方一致する",
    },
    "form[name='bidform'] input[type='submit']",
    "text=入札する",
  ],
  priceInput: [
    selectors.priceInput,
    // 2026-08-28 実測: 入力欄は type=tel で **name 属性が無い**。
    // name を当てにした候補(Bid_price / bidYen / price)は実在しなかったので消した。
    // 実在しない候補を残すと、永久に0件なのが「まだ検証していないだけ」に見える(地雷7)
    "input[type='tel']",
    {
      sel: "input[type='text']",
      // ページ上部のヘッダ検索窓(#mhdSearchBoxInput)に当たる。
      // 入札額をここに入れても画面は何も言わない
      trap: "ヘッダの検索窓 #mhdSearchBoxInput に当たる",
    },
  ],
  bidConfirmButton: [
    selectors.bidConfirmButton,
    // 2026-08-28 実測: 表示は「確認する」。<button> なので submit input は無い
    "button:has-text('確認')",
  ],
  bidSubmitButton: [
    // ⚠️ 確定ボタンの文言は **商品によって変わる**。実測2種:
    //   2026-08-28 21:00 「上記のガイドライン等、情報提供に同意して 入札する」
    //   2026-08-28 22:44 「上記に同意のうえ入札する」
    //   2026-08-29 00:35 「上記に同意のうえ 入札する」(ヒット1件で確定)
    // 1商品で見た文言を固定値にすると、別商品でヒット0件になって入札が
    // 成立しない(実際に2回失敗した)。共通部は「同意」と「入札する」だけ。
    selectors.bidSubmitButton,
    'role=button[name="上記のガイドライン等、情報提供に同意して 入札する"]',
    'role=button[name="上記に同意のうえ入札する"]',
    {
      sel: 'role=button[name="入札する"]',
      // 確認画面でも2件当たる。裏の商品ページのボタンで、押しても入札は
      // 成立しないのに ✅ に見える(2026-08-28 に実際そう出た)
      trap: "確認画面でも裏の商品ページのボタン2件に当たる",
    },
    {
      sel: "button:has-text('入札する')",
      // 裏2件 + 本物1件 = 3件。数が合うかで上の判断を裏取りするために残すが、
      // **先頭は裏のボタン**なので罠。2026-08-29 実測で3件を確認済み。
      // 罠に印を付けないと ✅ 判定(全候補が同じ要素を指すか)に混ざり、
      // 本命が1件で当たっているのに「2種類ある」の ⚠️ が毎回出る。
      trap: "先頭が裏の商品ページのボタン(実測3件 = 裏2 + 本物1)",
    },
    {
      sel: "input[type='submit'][value*='入札']",
      // 2026-08-28 実測で0件。<button> なので submit input は存在しない
      trap: "実測0件(確定ボタンは <button>)",
    },
  ],
  wonIndicator: [selectors.wonIndicator, "text=落札しました"],
  highestBidderIndicator: [
    selectors.highestBidderIndicator,
    "text=最高額入札者",
  ],
  outbidIndicator: [selectors.outbidIndicator, "text=高値更新"],
  watchlistLoginWall: [
    selectors.watchlistLoginWall,
    // ↓ 2026-08-29 の実測で **全て0件**。消さずに残すのは、消すと
    // 「試したが無かった」が記録から消えて、次に誰かが同じ形を書き直すから。
    "form[action*='login.yahoo.co.jp']",
    "input[name='login']",
    "text=ログインしてください",
    {
      sel: "text=ログイン",
      // 3件当たるが、1件は「パスワードのみでのログインを終了します」。
      // 部分一致なので壁の判定には使えない(実測 2026-08-29)。
      trap: "部分一致で別の文にも当たる(実測3件・うち1件は無関係な案内文)",
    },
  ],
  watchlistItemLink: [
    selectors.watchlistItemLink,
    "a[href*='/jp/auction/']",
    {
      sel: "li a[href*='auction']",
      // 2026-08-25 実測: これが ✅ として報告されたが、実体は
      // cm-Footer__serviceLink(「ガイドライン」「特定商取引法の表示」)だった
      trap: "フッターの auctions.yahoo.co.jp リンクを拾う",
    },
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
// 入札フォームで確認したいスロット(Stage 2 の確認ボタンを押す前に見る)
//
// ⚠️ bidSubmitButton を **ここに入れないこと**。2026-08-28 の実測で、
// 入札フォームはモーダル(URL が変わらない)で、裏の商品ページの
// 「入札する」ボタン2件が DOM に残ったままだと分かった。確認画面に
// 着いていないのに `role=button[name="入札する"]` が2件当たり、
// レポートには **✅ 検証済に見える偽陽性**が出る(実際にそう出た)。
// 確定ボタンは「確認ボタンを押した後」にだけ意味がある。
const STAGE2_SLOTS = ["priceInput", "bidConfirmButton"];
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
  /** 実際に入札する。取り消せない */
  stage3: boolean;
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
    stage3: false,
    watchlist: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--headless") args.headless = true;
    else if (a === "--anonymous") args.anonymous = true;
    else if (a === "--stage2") args.stage2 = true;
    else if (a === "--stage3") args.stage3 = true;
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
  if (args.stage3) {
    if (args.stage2) throw new Error("--stage2 と --stage3 は併用できない(先に Stage 2 で測ること)");
    if (args.watchlist) throw new Error("--watchlist と --stage3 は併用できない");
    if (args.anonymous) throw new Error("--anonymous では入札できない");
    if (!(args.amount && args.amount > 0)) throw new Error("--stage3 には --amount <入札額> が必須");
    // 検証のための道具なので、金額の上限を置く。ここを外して大きい額を入れると
    // 「セレクタが正しいか確かめる」ためだけに落札してしまう。
    if (args.amount > STAGE3_MAX_AMOUNT) {
      throw new Error(
        `--stage3 の入札額は ${STAGE3_MAX_AMOUNT} 円までに制限してある(指定: ${args.amount} 円)。` +
          "これは確定クリックが本当に効くかを確かめるための道具で、実運用の入札には使わない。",
      );
    }
  }
  return args;
}

/**
 * Stage 3 で許す入札額の上限(円)。
 * 確定クリックが効くかを確かめるだけの道具なので、落札してしまっても
 * 痛くない額に制限する。実運用の入札はアプリ本体から行う。
 */
const STAGE3_MAX_AMOUNT = 1_000;

const JST = "Asia/Tokyo";
const fmt = (d: Date | undefined) =>
  d ? d.toLocaleString("ja-JP", { timeZone: JST }) : "(取得できず)";

const out: string[] = [];
/**
 * 途中で落ちても・ブラウザを閉じられてもレポートだけは残すための書き出し口。
 * main() が reportPath を決めた時点で実体が入る。
 */
let saveReport: () => void = () => {};
let reportAnnounced = false;

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
  /** 罠と分かっている候補ならその理由。通常候補は undefined */
  trap?: string;
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
  for (const cand of CANDIDATES[slot] ?? []) {
    const selector = typeof cand === "string" ? cand : cand.sel;
    const trap = typeof cand === "string" ? undefined : cand.trap;
    try {
      const loc = page.locator(selector);
      const count = await loc.count();
      if (count === 0) {
        results.push({ selector, trap, count: 0, visible: false, text: "", nodes: [] });
        continue;
      }
      const first = loc.first();
      const visible = await first.isVisible().catch(() => false);
      const nodes: NodeDesc[] = [];
      for (let i = 0; i < Math.min(count, NODES_PER_CANDIDATE); i++) {
        nodes.push(await describeNode(loc.nth(i)));
      }
      results.push({ selector, trap, count, visible, text: nodes[0]?.text ?? "", nodes });
    } catch (err) {
      // セレクタ構文自体が通らない場合もここに来る
      results.push({
        selector,
        trap,
        count: -1,
        visible: false,
        text: err instanceof Error ? err.message.slice(0, 60) : String(err),
        nodes: [],
      });
    }
  }
  return results;
}

/**
 * そのスロットで「採用してよい」当たり候補。
 * 罠と分かっている候補は当たっても採らない(2026-08-25 に押してしまった経路)。
 */
function usableHits(results: SlotResult[]): SlotResult[] {
  return results.filter((r) => r.count > 0 && r.visible && !r.trap);
}

async function reportSlots(page: Page, slots: string[]): Promise<void> {
  for (const slot of slots) {
    const results = await probeSlot(page, slot);
    const hits = usableHits(results);
    const trapHits = results.filter((r) => r.count > 0 && r.trap);
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
    say("| 候補 | 件数 | 可視 | 罠 | テキスト |");
    say("|---|---|---|---|---|");
    for (const r of results) {
      const n = r.count < 0 ? "err" : String(r.count);
      say(
        `| \`${r.selector}\` | ${n} | ${r.visible ? "○" : "-"} | ${r.trap ? "🪤 " + r.trap : ""} | ${r.text} |`,
      );
    }
    say("");
    if (trapHits.length > 0) {
      say(
        "> 🪤 罠と分かっている候補が当たっている。**これは ✅ に数えていないし、" +
          "クリック対象にも選ばれない。** selectors.ts に写さないこと。",
      );
      say("");
    }
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

/**
 * CSR の描画を待ってから、描画できているかを報告する。
 *
 * 2026-08-25 の実測で分かったこと(pageReady.ts の冒頭も読むこと):
 * ヤフオクの新UIはクライアントサイドレンダリング。`domcontentloaded` の直後は
 * DOM がほぼ空で、その状態で候補を試すと **セレクタが正しくても全部0件** になる。
 *
 * ⚠️ ここが無いと、レポートの「❌ 全滅」が
 *   (a) セレクタが違う   (b) まだ描画されていない
 * のどちらなのか永久に区別できない。落ちようがない検証と同じで、
 * 当たりようがない検証になっていた。
 *
 * 待ち方は networkidle 頼みにしない。広告・計測ビーコンが鳴り続けるページでは
 * networkidle が来ないので、**要素数が増えなくなったこと** を主な合図にする。
 */
// ⚠️ 待ち方の実体は src/bidder/settle.ts に置いてある。
//    ここに写しを持たないこと — プローブだけ直して本番の同期が古いままになる。
//    2026-08-27 まで実際にそうなっていて、同じページをプローブは商品リンク148本、
//    同期は回によって9〜33件と、別々のものを見ていた。
async function settle(page: Page, label: string): Promise<void> {
  const { clickable, inputs, elapsedMs, verdict: v } = await settlePage(page);
  say(
    `_描画待ち(${label}): ${elapsedMs}ms / クリック要素 ${clickable} / input ${inputs}_`,
  );
  say("");
  if (!v.rendered) {
    say(`> ⚠️ **まだ描画されていない可能性がある** — ${v.reason}`);
    say("");
    say(
      "> この状態で下に出る「❌ 全滅」は、セレクタが違う証拠にならない。" +
        "スクリーンショットを見て、本当に中身が出ているか確かめること。",
    );
    say("");
  }
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

/** 祖先をたどる深さ。ヤフオクの新UIは入れ子が深いので余裕を持たせる */
const ANCESTRY_DEPTH = 14;

/**
 * 当たった要素が **ページのどのブロックに居るか** を出す。
 *
 * なぜ要るか(2026-08-26): `a[href*="/jp/auction/"]` はウォッチリストの
 * 一覧と、同じページに載っている「おすすめ」カルーセルの **両方** に当たる。
 * 件数だけ見ていると 64件/71件のような「それらしい数」が返り、
 * `scrapeWatchlistPage` は OK を返してしまう。
 * どのコンテナに何件入っているかが分かれば、一覧だけを指す
 * スコープ付きセレクタが書ける。
 *
 * class 名はビルドごとに変わるハッシュ(`gv-Carousel__button--WaNfn7Xe...`)
 * なので、`--` の前だけを使う。`sc-` / `css-` で始まる styled-components の
 * 自動生成クラスは意味を持たないので落とす。
 */
/**
 * カルーセル除外が効いているかを数で出す。
 *
 * ⚠️ 「当たった件数」だけを見ていると、**多いほど成功に見える** という
 *    一番まずい向きに壊れる。実際 2026-08-27 まで、70件拾えているのに
 *    ウォッチ中は9件だけ、という状態が「✅ 当たった」と報告されていた。
 */
async function scopeReport(page: Page): Promise<void> {
  const total = await page.locator(selectors.watchlistItemLink).count();
  const containers = await page.locator(CAROUSEL_ANCESTOR_SELECTOR).count();
  const kept = await page
    .locator(selectors.watchlistItemLink)
    .evaluateAll((els, sel: string) => els.filter((e) => e.closest(sel) === null).length,
      CAROUSEL_ANCESTOR_SELECTOR);
  const v = watchlistScopeVerdict({ total, kept, carouselContainers: containers });

  say("**watchlistItemLink: カルーセル除外の内訳**");
  say("");
  say("| 項目 | 件数 |");
  say("|---|---|");
  say(`| 商品リンク(除外前) | ${total} |`);
  say(`| うちカルーセルの中 | ${total - kept} |`);
  say(`| **ウォッチ中として採用** | **${kept}** |`);
  say(`| ページ上のカルーセル要素 | ${containers} |`);
  say("");
  if (v.ok) {
    say(`- ✅ スコープは効いている(除外条件: \`${CAROUSEL_ANCESTOR_SELECTOR}\`)`);
  } else {
    say(`- 🚨 **スコープが効いていない**: ${v.reason}`);
  }
  say("");
}

async function ancestryReport(page: Page, sel: string, label: string): Promise<void> {
  say(`**${label}: 当たった要素の所属ブロック**`);
  say("");

  const chains = await page
    .locator(sel)
    .evaluateAll(
      (els, depth) =>
        els.map((e) => {
          const names: string[] = [];
          let node = e.parentElement;
          for (let i = 0; i < depth && node; i += 1) {
            const cls = (node.getAttribute("class") ?? "")
              .split(/\s+/)
              .map((c: string) => c.split("--")[0])
              .filter((c: string) => c.length > 0 && !/^(sc|css)-/.test(c));
            if (cls.length > 0 && !names.includes(cls[0])) names.push(cls[0]);
            node = node.parentElement;
          }
          return names.join(" < ") || "(意味のあるclassが無い)";
        }),
      ANCESTRY_DEPTH,
    );

  const counts = new Map<string, number>();
  for (const c of chains) counts.set(c, (counts.get(c) ?? 0) + 1);
  const rows = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);

  say("| 件数 | 祖先のクラス(内側 → 外側) |");
  say("|---|---|");
  for (const [chain, n] of rows) say(`| ${n} | \`${chain}\` |`);
  say("");
  if (rows.length > 1) {
    say(
      "- ⚠️ **所属ブロックが複数ある = 別々の一覧を混ぜて拾っている**。" +
        "一覧だけを指すようにスコープを付けること",
    );
    say("");
  }
}

/** ウォッチリスト導線を探しに行くページ(ログイン後に必ず開けるもの) */
const WATCHLIST_LINK_SOURCES = [
  "https://auctions.yahoo.co.jp/",
  "https://auctions.yahoo.co.jp/jp/show/mystatus",
];

/**
 * ウォッチリストの URL を **ヤフオク自身に吐かせる**。
 *
 * なぜ URL 候補を増やすのではなくこれをやるか(2026-08-26):
 * 候補に入れていた2つの URL はどちらも存在しなかった。推測を足していく方法は
 * 「外れたときに何も分からない」上に、外れた候補が404案内ページを返すせいで
 * 「ウォッチリストが空」と見分けが付かない出力になる。
 * トップページやマイオークションには必ずウォッチリストへの導線があるので、
 * そのリンクの href を読めば **推測せずに** 正解が手に入る。
 *
 * ⚠️ href はレポートに書き出すので redactUrl を通す。ヤフオクの導線 URL には
 * `.done=` や `crumb` が乗る(設計 §8: 秘匿情報をログに残さない)。
 */
async function discoverWatchlistLinks(page: Page): Promise<void> {
  say("## ウォッチリスト導線の探索(ヤフオクのページからリンクを読む)");
  say("");

  for (const src of WATCHLIST_LINK_SOURCES) {
    say(`### 探索元: ${src}`);
    say("");
    try {
      await page.goto(src, { waitUntil: "domcontentloaded" });
    } catch (err) {
      say(`- ⚠️ 遷移に失敗: ${err instanceof Error ? err.message : String(err)}`);
      say("");
      continue;
    }
    await settle(page, `探索元 ${src}`);

    const links = await page
      .locator("a[href]")
      .evaluateAll((els) =>
        els.map((e) => ({
          href: e.getAttribute("href") ?? "",
          text: (e.textContent ?? "").replace(/\s+/g, " ").trim(),
        })),
      );

    const pageUrl = page.url();
    const hits: { text: string; url: string }[] = [];
    const seen = new Set<string>();
    for (const l of links) {
      if (!l.href) continue;
      // 表示文字とURLの両方を見る。アイコンだけのリンクは文字が空になるので
      // href 側だけで当たることがある
      const looksWatch = l.text.includes("ウォッチ") || /watch/i.test(l.href);
      if (!looksWatch) continue;
      let abs = "";
      try {
        abs = new URL(l.href, pageUrl).toString();
      } catch {
        continue;
      }
      const safe = redactUrl(abs);
      const key = `${l.text}|${safe}`;
      if (seen.has(key)) continue;
      seen.add(key);
      hits.push({ text: l.text || "(文字なし)", url: safe });
    }

    if (hits.length === 0) {
      say("- ❌ 「ウォッチ」を含むリンクが1つも無い");
      say(`  - 参考: このページのリンク総数 ${links.length}件`);
    } else {
      say("| 表示文字 | href(秘匿値は伏せてある) |");
      say("|---|---|");
      for (const h of hits.slice(0, 20)) {
        say(`| ${h.text} | \`${h.url}\` |`);
      }
      say("");
      say("- ⬆️ **これが WATCHLIST_URL_CANDIDATES に入れるべき URL**");
    }
    say("");
  }
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
  // 候補を試す前に、正解の URL をヤフオク自身から取りに行く。
  // 候補が全滅しても、ここに答えが出ていれば次の一手が決まる。
  await discoverWatchlistLinks(page);

  for (const [idx, url] of WATCHLIST_URL_CANDIDATES.entries()) {
    say(`## 候補URL ${idx + 1}: ${url}`);
    say("");

    const t0 = Date.now();
    let httpStatus: number | null = null;
    try {
      const res = await page.goto(url, { waitUntil: "domcontentloaded" });
      httpStatus = res?.status() ?? null;
    } catch (err) {
      say(`- ⚠️ 遷移に失敗: ${err instanceof Error ? err.message : String(err)}`);
      say("");
      continue;
    }
    say(`- 到達URL: ${page.url()}`);
    say(`- HTTPステータス: ${httpStatus ?? "(取れず)"}`);
    say(`- ページタイトル: ${await page.title()}`);
    say(`- 所要: ${Date.now() - t0}ms`);
    say("");
    await settle(page, `ウォッチリスト候補${idx + 1}`);

    // ⚠️ セレクタの当たり外れを見る前に、そもそもどこに着いたかを言う。
    // 存在しない URL の案内ページは商品リンク0件になるので、これが無いと
    // 「セレクタが外れた」と「URL が無い」を取り違える(2026-08-26 に発生)
    const identity = pageIdentityVerdict({
      url: page.url(),
      httpStatus,
      bodyText: await page.locator("body").innerText().catch(() => ""),
    });
    if (identity.kind === "NOT_FOUND") {
      say(`- 🪦 **この URL は存在しない**: ${identity.reason}`);
      say("  - 以下のセレクタ全滅は「セレクタが違う」証拠にならない");
    } else if (identity.kind === "LOGIN_REQUIRED") {
      say(
        anonymous
          ? `- ✅ 未ログインでログイン画面へ飛んだ(= ログイン必須の陽性対照): ${identity.reason}`
          : `- ⚠️ **ログイン画面へリダイレクトされた = Cookie が失効している**: ${identity.reason}`,
      );
    } else {
      say("- ✅ 404でもログイン画面でもない = 中身のあるページに着いている");
      if (anonymous) {
        say("  - ⚠️ 未ログインなのにログイン画面へ飛ばされていない。ログイン必須のページではない可能性");
      }
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
    const result = await scrapeWatchlistPage(page, httpStatus);
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

    // ⚠️ 件数が「それらしい」だけでは合格にしない。同じページをもう一度読んで
    // 件数が変われば、遅延読み込みされる別の一覧を巻き込んでいる。
    // 2026-08-26 はこれで 64件 → 71件 のブレを検出した。
    if (result.kind === "OK") {
      await page.reload({ waitUntil: "domcontentloaded" });
      await settle(page, `再読込(候補${idx + 1})`);
      const again = await scrapeWatchlistPage(page, httpStatus);
      const stab = listStabilityVerdict({ first: result.itemCount, second: again.itemCount });
      if (stab.stable) {
        // ⚠️ 一致は合格の根拠にならない。2026-08-27 の実測では、
        // おすすめカルーセル65商品を巻き込んだまま 70件 → 70件 で一致した。
        // 描画が落ち着いた後ならカルーセルも安定するため。
        say(`- 再読込でも ${again.itemCount}件で一致(**一致は合格の根拠ではない** — 下のスコープ内訳を見ること)`);
      } else {
        say(`- 🚨 **件数が安定しない**: ${stab.reason}`);
        say("  - この `watchlistItemLink` を selectors.ts に ✅ として写さないこと");
      }
      say("");
      await scopeReport(page);
      await ancestryReport(page, selectors.watchlistItemLink, "watchlistItemLink");
    }

    await discovery(page);

    const shot = reportPath.replace(/\.md$/, `-wl${idx + 1}.png`);
    await page.screenshot({ path: shot, fullPage: false }).catch(() => {});
  }

  say("### 次にやること");
  say("");
  say("- 「ウォッチリスト導線の探索」で出た URL を WATCHLIST_URL_CANDIDATES に入れる(推測で足さない)");
  say("- `scrapeWatchlistPage` が OK を返した候補URLを WATCHLIST_URL_CANDIDATES の先頭にする");
  say("- 当たったセレクタを selectors.ts に書き、状態表を ✅ に更新する");
  say("- `--anonymous` の回で watchlistLoginWall が当たっていることを確認する(陰陽の対照)");
  say("");
}

// 認証済み DOM に対してパーサが機能するかを見る(未認証 fetch とは差が出うる)
async function reportParser(
  page: Page,
  url: string,
  anonymous: boolean,
): Promise<ReturnType<typeof parseAuctionPage>> {
  const html = await page.content();
  const info = parseAuctionPage(html, url);
  // 即決価格を **2つの経路で出す**。2026-08-29 に決着済み:
  //   埋め込みJSON の bidOrBuyPrice は税抜(8100)、taxinBidorbuy が税込(8910)。
  //   ページの表示は税込(「即決 8,910円(税込)」)。個人出品は税キーが無く一致。
  // パーサは税込を採るので、以降この2行は **一致するのが正常**。
  // ずれたら、税の扱いかタグの形が変わったということ。
  //
  // ⚠️ 表示テキスト側はタグを剥がしてから当てる。生HTMLだと
  //    `即決</dt><dd class="sc-1f0603b0-1 ...">44,000<!-- -->円` のように
  //    クラス名の数字とタグが挟まって **構造上ぜったいに当たらない**
  //    (2026-08-29 以前はここが常に「見つからず」だった)。
  const flatText = html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
  const textBin = flatText.match(/即決(?:価格)?[^0-9]{0,20}([\d,]+)\s*円/);
  say(`### パーサ結果(${anonymous ? "未ログイン" : "認証済み"} DOM)`);
  say("");
  say("| 項目 | 値 |");
  say("|---|---|");
  say(`| title | ${info.title ?? "(取得できず)"} |`);
  say(`| currentPrice | ${info.currentPrice ?? "(取得できず)"} |`);
  // 「今すぐ落札」があるのに (取得できず) なら抽出が壊れている。
  say(`| buyNowPrice (パーサ) | ${info.buyNowPrice ?? "(取得できず / 即決なし)"} |`);
  say(`| buyNowPrice (表示テキスト) | ${textBin ? textBin[1] : "(見つからず)"} |`);
  say(`| endAt (JST) | ${fmt(info.endAt)} |`);
  say(`| hasAutoExtension | ${info.hasAutoExtension ?? "(取得できず)"} |`);
  say(`| sellerName | ${info.sellerName ?? "(取得できず)"} |`);
  say(`| isClosed | ${info.isClosed ?? "(取得できず)"} |`);
  say("");
  const textBinNum = textBin ? Number(textBin[1].replaceAll(",", "")) : undefined;
  if (info.buyNowPrice !== undefined && textBinNum !== undefined && info.buyNowPrice !== textBinNum) {
    const ratio = (textBinNum / info.buyNowPrice).toFixed(3);
    say(
      `> ⚠️ パーサと表示で即決価格が違う(パーサ ${info.buyNowPrice} / 表示 ${textBinNum}・比 ${ratio})。` +
        "2026-08-29 以降、パーサは税込(taxinBidorbuy)を採るので **一致するのが正常**。" +
        "比が 1.100 前後なら税抜が漏れている(taxin 系のキー名が変わった可能性)。",
    );
    say("");
  }
  if (info.endAt === undefined || info.currentPrice === undefined) {
    say("> ⚠️ 終了時刻か現在価格が取れていない。ここが取れないと監視ジョブが機能しない。");
    say("");
  }
  return info;
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
  // ⚠️ 以前は最後に1回だけ書いていた。Stage 2 は最後に「Enter で閉じる」待ちに
  //    入るので、**ブラウザの窓を閉じた回・Ctrl-C で抜けた回はレポートが
  //    1バイトも残らなかった**(2026-08-27/28 の2回とも消えた。png だけ残る)。
  //    P0 は実ページを1回開くたびに手が要る作業なので、取り直しの代償が高い。
  //    以後は「書ける時点で毎回書く」。out は追記しかしないので上書きで良い。
  saveReport = () => {
    writeFileSync(reportPath, out.join("\n"), "utf-8");
    if (!reportAnnounced) console.log(`\nレポート: ${reportPath}`);
    reportAnnounced = true;
  };

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
        : args.stage3
          ? "**3 (実入札。取り消せない)**"
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
    saveReport();
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
  say("");
  await settle(page, "商品ページ");
  if (/login\.yahoo\.co\.jp/.test(page.url())) {
    say("- ⚠️ **ログイン画面へリダイレクトされた = Cookie が失効している**");
  }
  say("");

  await reportSlots(page, STAGE1_SLOTS);
  const parsed = await reportParser(page, args.url, args.anonymous);
  await discovery(page);

  const shot1 = reportPath.replace(/\.md$/, "-stage1.png");
  await page.screenshot({ path: shot1 }).catch(() => {});

  if (args.watchMinutes && args.watchMinutes > 0) {
    await watchExtension(page, args.url, args.watchMinutes);
  }

  if (args.stage3) {
    say("## Stage 3 — 実入札(取り消せない)");
    say("");
    say("> worker が本番で使う `placeBid()` をそのまま呼ぶ。プローブ独自の経路は通らない。");
    say("> 4点ガード(確定ボタンが見つかる / 入力欄が消えている / ラベルが商品ページ側でない /");
    say("> 最初に押した入札ボタンと別要素)を全部通らないと押さない。");
    say("");

    // 取り消せない操作なので、実行の意思を毎回タイプで取る。
    // `--stage3` を打ったこと自体を同意とみなさない(履歴からの再実行で飛ぶ)。
    if (!process.stdin.isTTY) {
      throw new Error("--stage3 は対話端末からのみ実行できる(実行の確認をタイプで取るため)");
    }
    const rl = createInterface({ input: process.stdin, output: process.stdout });
    const answer = await rl.question(
      `\n>>> ${args.url}\n` +
        `>>> に ${args.amount} 円で **実際に入札** する。取り消せない。\n` +
        `>>> 誰も上回らなければ落札になり、送料を含めて支払い義務が発生する。\n` +
        `>>> 実行するなら「入札する」とタイプして Enter (それ以外は中止): `,
    );
    rl.close();

    if (answer.trim() !== "入札する") {
      say(`- 中止した(入力: ${JSON.stringify(answer.trim())})`);
      say("");
      console.log(">>> 中止した。入札していない。");
    } else {
      const bidPage = await context.newPage();
      const t = Date.now();
      const result = await placeBid(bidPage, args.url, args.amount as number, 20_000, {
        dryRun: false,
      });
      const detail = "detail" in result ? result.detail : "";
      say(`- placeBid の戻り: **${result.outcome}** (${Date.now() - t}ms)`);
      say(`- detail: ${detail || "(なし)"}`);
      say("");
      await bidPage
        .screenshot({ path: reportPath.replace(/\.md$/, "-stage3-after-click.png") })
        .catch(() => {});

      // ⚠️ SUCCESS は「押せてページが読み込まれた」までしか意味しない。
      // 入札が成立した証拠は商品ページ側にしか無いので、必ず読み戻す。
      // (押せたことを成功の根拠にすると、裏のボタンを押した回も成功に見える)
      say("### 読み戻し — 入札が本当に成立したか");
      say("");
      await bidPage.goto(args.url, { waitUntil: "domcontentloaded" }).catch(() => {});
      await settle(bidPage, "入札後の商品ページ");
      await reportSlots(bidPage, [
        "highestBidderIndicator",
        "outbidIndicator",
        "loggedInIndicator",
      ]);
      await reportParser(bidPage, args.url, false);
      await bidPage
        .screenshot({ path: reportPath.replace(/\.md$/, "-stage3-readback.png") })
        .catch(() => {});
      say("");
      say("**判定**: `highestBidderIndicator` が当たっていれば、確定クリックは");
      say("本当に効いている。当たっていなければ、押せてはいるが入札は成立して");
      say("いない = セレクタが裏のボタンを掴んでいる。selectors.ts を ✅ にしないこと。");
      say("");
      say("⚠️ **現在価格を根拠にしない**。ヤフオクは自動入札なので、対抗者が");
      say("いなければ現在価格は開始価格のまま動かず、上がるのは自分の上限だけ。");
      say("2026-08-29 は 1円の商品に 11円で入札して成立したが、現在価格は 1円の");
      say("ままだった。「価格が上がっていないから失敗」と読むと逆の結論になる。");
      say("");
      console.log(`\n>>> placeBid: ${result.outcome} ${detail}`);
    }
    saveReport();
  }

  if (args.stage2) {
    say("## Stage 2 — 入札フォーム〜確認画面");
    say("");
    say("> **このスクリプトは確定ボタンを押さない。**");
    say("> 確認画面まで進めたらブラウザを開いたまま止めるので、確定するかどうかは人が決める。");
    say("");

    // --amount が最低入札額に届いていないと、確認ボタンを押した先はフォームの
    // 検証エラーで、確認画面には **絶対に着かない**。
    // ⚠️ 弾かれ方が地雷: 画面はモーダルのまま・URL も変わらないので、
    //    「セレクタが違う」「まだ描画されていない」と見分けがつかない。
    //    2026-08-28 に現在価格4,900円へ 4,901 を入れて回し、1往復を無駄にした
    //    (入札単位100円なので最低は5,000円。端数を足しただけでは足りない)。
    // ⚠️ この判定に使う入札単位の表(packages/shared/src/bidUnit.ts)自体が
    //    まだ P0 未検証。ここで止まったら、フォームが出す「最低入札価格」の
    //    表示と突き合わせて表の側を直すこと(合わせて表の検証にもなる)。
    const minAmount =
      parsed.currentPrice === undefined ? undefined : minimumBidToBeat(parsed.currentPrice);
    if (minAmount !== undefined && (args.amount ?? 0) < minAmount) {
      say(`### ⚠️ 入札額 ${args.amount} では進めない — 最低入札額は ${minAmount} 円`);
      say("");
      say(`- 現在価格: ${parsed.currentPrice} 円`);
      say(`- 入札単位: ${minAmount - parsed.currentPrice!} 円(bidUnit.ts の表による推定)`);
      say("");
      say("入札ボタンには触っていない。`--amount` を上げて回し直すこと。");
      say("");
      // ⚠️ 上の「ここで return するとレポートが残らない」に該当しないよう、
      //    先に書き出してから抜ける。
      saveReport();
      console.log(
        `\n>>> 入札額 ${args.amount} は最低入札額 ${minAmount} 円に届かない。` +
          `\n>>> --amount ${minAmount} 以上で回し直すこと(何もクリックしていない)。`,
      );
      await close();
      await prisma.$disconnect();
      return;
    }

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

    // 入札ボタン: Stage 1 で当たった候補を使う。
    // ⚠️ 罠と分かっている候補は選ばない(usableHits)。2026-08-25 はここで
    // `a[href*='/jp/show/bid']` が先頭に来て、入札履歴ページを開いた。
    // 最後に出す案内を実際の到達点に合わせるためのフラグ。
    // ⚠️ 以前は無条件に「確認画面で止めた」と出していた。着地に失敗した回でも
    //    そう出るので、**進めなかったことが端末上では分からなかった**
    //    (レポートには出ているが、その場で読むのは最後の2行)。
    let reachedConfirmScreen = false;
    const bidResults = await probeSlot(page, "bidButton");
    const bidHits = usableHits(bidResults);
    if (bidHits.length === 0) {
      const trapped = bidResults.filter((r) => r.count > 0 && r.trap);
      say("入札ボタンの候補が全滅しているため Stage 2 は進めない。上のダンプから候補を足すこと。");
      if (trapped.length > 0) {
        say("");
        say(
          `(罠と分かっている候補 ${trapped.map((r) => "\`" + r.selector + "\`").join(" / ")} ` +
            "は当たっているが、押さない)",
        );
      }
    } else {
      const bidSel = bidHits[0].selector;
      say(`使用した入札ボタン: \`${bidSel}\``);
      say("");
      const urlBeforeBid = page.url();
      const ok = await step("入札ボタンをクリック", async () => {
        await page.locator(bidSel).first().click({ timeout: 15_000 });
        await page.waitForLoadState("domcontentloaded", { timeout: 15_000 });
      });
      if (ok) {
        await settle(page, "入札ボタンをクリックした後");

        // 押した先が本当に入札フォームかを確かめる。
        // ⚠️ クリックが「成功」したことは、正しいページに着いたことを意味しない。
        // 2026-08-25 はクリック○(47ms)と報告しながら入札履歴を開いていて、
        // それが分かるのはこの後の全スロット全滅からだけだった。
        // その全滅は「まだ描画されていない」と見分けがつかない。
        const priceCount = usableHits(await probeSlot(page, "priceInput")).length;
        const landing = bidLandingVerdict({
          url: page.url(),
          priceInputCount: priceCount,
        });
        if (!landing.ok) {
          say(`### ⚠️ 入札フォームに着いていない — ${landing.reason}`);
          say("");
          say(`- クリック前: ${urlBeforeBid}`);
          say(`- クリック後: ${page.url()}`);
          say("");
          say(
            "**この先は進めない。** 使った候補が別の要素を指している可能性が高いので、" +
              "下のダンプを見て候補を直し、CANDIDATES の罠マークを足してから回し直すこと。",
          );
          say("");
          steps.push({
            name: "入札フォームに着地",
            ms: 0,
            ok: false,
            detail: landing.reason,
          });
          await discovery(page);
          await page
            .screenshot({ path: reportPath.replace(/\.md$/, "-landing.png") })
            .catch(() => {});
        }
        // ⚠️ ここで return すると下の writeFileSync に届かず、レポートが
        //    1バイトも残らない。着地に失敗した回こそレポートが要る。
        if (landing.ok) {
          await reportSlots(page, STAGE2_SLOTS);
          await discovery(page);
          const priceHits = (await probeSlot(page, "priceInput")).filter(
            (r) => r.count > 0 && !r.trap,
          );
          if (priceHits.length > 0) {
            await step(`入札額 ${args.amount} を入力`, async () => {
              await page.locator(priceHits[0].selector).first().fill(String(args.amount), {
                timeout: 15_000,
              });
            });
          }
          const confirmHits = usableHits(await probeSlot(page, "bidConfirmButton"));
          // 押す前に「それは確定ボタンではないか」を確かめる。
          // この時点で入札額は入力済みなので、確定ボタンを押すと **実入札が飛ぶ**。
          // 押してよいかを未検証のセレクタの正しさに委ねない(probeSafety.ts)。
          const submitKeys = (await probeSlot(page, "bidSubmitButton"))
            .filter((r) => r.count > 0)
            .flatMap((r) => r.nodes.map(nodeKey));
          const confirmNode = confirmHits[0]?.nodes[0];
          const verdict = confirmHits.length === 0 || !confirmNode
            ? { safe: false, reason: "確認ボタンの候補が全滅している" }
            : confirmClickVerdict({
                confirmKey: nodeKey(confirmNode),
                submitKeys,
                label: confirmNode.text || confirmNode.value,
              });

          if (!verdict.safe) {
            say(`### ⚠️ 確認ボタンを押さずに止めた — ${verdict.reason}`);
            say("");
            say("入札額は入力済みだが、ここから先へは自動では進めない。");
            say("上のダンプで実体を確認し、確認ボタンだと判断できたら **画面上で自分で押すこと**。");
            say("");
            steps.push({ name: "確認画面へ進む", ms: 0, ok: false, detail: verdict.reason });
          } else {
            await step("確認画面へ進む", async () => {
              await page.locator(confirmHits[0].selector).first().click({ timeout: 15_000 });
              await page.waitForLoadState("domcontentloaded", { timeout: 15_000 });
            });
            await settle(page, "確認ボタンをクリックした後");
            reachedConfirmScreen = true;
            say("### 確認画面のスロット");
            say("");
            await reportSlots(page, ["bidSubmitButton"]);
            await discovery(page);
          }
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
    // 対話待ちの **前** に書く。ここを越えられるかは人の操作次第。
    saveReport();

    if (!args.headless) {
      console.log(
        reachedConfirmScreen
          ? "\n>>> 確認画面で止めた。確定するなら画面上で自分でクリックすること。\n>>> 終わったら Enter を押すとブラウザを閉じる。"
          : "\n>>> 確認画面までは進めていない(上のレポートの ⚠️ を読むこと)。\n>>> ブラウザは開いたままなので、画面の実物を見てから Enter で閉じる。",
      );
      const rl = createInterface({ input: process.stdin, output: process.stdout });
      await rl.question("");
      rl.close();
    }
  }

  saveReport();

  await close();
  await prisma.$disconnect();
}

main().catch(async (err) => {
  console.error("[p0-probe]", err instanceof Error ? err.message : err);
  // 落ちた回こそレポートが要る(ブラウザを閉じられた回もここに来る)
  try {
    saveReport();
  } catch {
    // 書き出し先が作られる前に落ちたときは諦める
  }
  await prisma.$disconnect().catch(() => {});
  process.exit(1);
});
