// =============================================================
// 入札の入口だけを、**本番と同じ経路で**開いて計測する(読むだけ)。
//
// 目的: 2026-09-02 の実入札(k1242598835)が「15秒待って入札ボタン0件」で
// 失敗した件の切り分け。同じ日に P0 プローブ(Mac・headless あり/なし両方)では
// 同じセレクタが2件・可視で当たったので、残る差は **ワーカーの実行環境**
// (Docker コンテナ・イメージ同梱の Chromium・session.ts の起動オプション)か、
// **その商品固有の状態**しかない。
//
// プローブは自前で Chromium を起動する(scripts/p0-probe.ts の launchContext)
// ので、コンテナ側を試すのには使えない。ここは入札が実際に通る経路である
// bidder/session.ts の launchBrowser / createYahooContext をそのまま使う。
//
// ⚠️ **クリックは一切しない**。開いて数えて出すだけ。入札は起きない。
//
// 使い方(コンテナの中で実行する = ワーカーと同じ環境で測る):
//   docker compose exec worker npx tsx apps/worker/scripts/bid-entry-check.ts <商品URL>
// Mac 側で実行すればプローブと同じ環境になるので、両方走らせて差を見る。
//
// 終了コード: 入札ボタンが1件以上なら 0 / 0件なら 1(繰り返し回して
// 「たまに0件になる」型の故障を捕まえるため)。
// =============================================================
import "../src/env";
import { prisma } from "@yar/db";
import { createYahooContext, launchBrowser } from "../src/bidder/session";
import { captureBidEntry } from "../src/bidder/diagnose";
import { selectors } from "../src/bidder/selectors";
import { settlePage } from "../src/bidder/settle";

async function main(): Promise<number> {
  const url = process.argv[2];
  if (!url) {
    console.error("使い方: bid-entry-check.ts <商品URL> [セッションID]");
    return 2;
  }
  const sessionId = process.argv[3];
  const session = sessionId
    ? await prisma.yahooSession.findUnique({ where: { id: sessionId } })
    : await prisma.yahooSession.findFirst({
        where: { status: "ACTIVE" },
        orderBy: { createdAt: "asc" },
      });
  if (!session) {
    console.error("使えるヤフオク連携が無い(ACTIVE のセッションが0件)");
    return 2;
  }
  console.log(`連携: ${session.label} (${session.status})`);

  const browser = await launchBrowser();
  try {
    const context = await createYahooContext(browser, session.id);
    const page = await context.newPage();
    const startedAt = Date.now();
    await page.goto(url, { waitUntil: "domcontentloaded" });
    // 本番の監視ジョブと同じ待ち方(jobs/monitor.ts のウォームアップと同じ)
    const settled = await settlePage(page).catch(() => null);
    console.log(`到達URL: ${page.url()}`);
    console.log(
      settled
        ? `描画待ち: ${settled.elapsedMs}ms / クリック要素 ${settled.clickable} / 入力欄 ${settled.inputs} / 判定 ${settled.verdict.rendered ? "OK" : `NG(${settled.verdict.reason})`}`
        : "描画待ち: 計測できず",
    );
    // 入札を止める側の判定(placeBid の SESSION_EXPIRED ゲートと同じ条件)
    const loginVisible = await page
      .locator(selectors.loginLink)
      .first()
      .isVisible()
      .catch(() => false);
    console.log(`ログインリンクが見えている(=未ログイン扱い): ${loginVisible}`);
    const hits = await page.locator(selectors.bidButton).count().catch(() => -1);
    console.log(`入札ボタン(${selectors.bidButton}): ${hits}件`);
    console.log(await captureBidEntry(page));
    console.log(`所要: ${Date.now() - startedAt}ms`);
    return hits > 0 ? 0 : 1;
  } finally {
    await browser.close().catch(() => {});
    await prisma.$disconnect().catch(() => {});
  }
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(err);
    process.exit(2);
  });
