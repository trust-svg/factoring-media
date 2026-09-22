import { chromium, type Browser, type BrowserContext } from "playwright";
import {
  decryptSecret,
  encryptSecret,
  planCookieRefresh,
  toYahooCookies,
  type YahooCookie,
} from "@yar/shared";
import { prisma } from "@yar/db";

export async function launchBrowser(): Promise<Browser> {
  return await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
  });
}

// 暗号化保管されたCookieを復号してブラウザコンテキストへ注入する。
// 復号結果はこの関数のスコープ外に持ち出さない(設計 §8)。
export async function createYahooContext(
  browser: Browser,
  yahooSessionId: string,
): Promise<BrowserContext> {
  const session = await prisma.yahooSession.findUniqueOrThrow({
    where: { id: yahooSessionId },
  });
  const cookies = JSON.parse(decryptSecret(session.encryptedCookie)) as YahooCookie[];

  const context = await browser.newContext({
    locale: "ja-JP",
    timezoneId: "Asia/Tokyo",
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
  return context;
}

export async function markSessionExpired(yahooSessionId: string): Promise<void> {
  await prisma.yahooSession.update({
    where: { id: yahooSessionId },
    data: { status: "EXPIRED" },
  });
}

/**
 * ブラウザが持っている最新の Cookie を保管し直す(セッション延命)。
 *
 * 普通のブラウザなら使うたびに Cookie が更新されるが、このアプリは毎回
 * 保管済みスナップショットを注入して捨てていたので、連携は **登録した日の
 * まま歳を取り** 約4週間で切れていた(2026-09-21 に入札1件を落とし損ねた)。
 * ここで書き戻すことで、ウォッチリスト同期(1時間ごと)のたびに若返る。
 *
 * ⚠️ **ログインが生きていると分かっている経路からだけ呼ぶこと。**
 * ログイン画面へ飛ばされた後の一式を書き戻すと、生きているスナップショットを
 * 自分で潰す。保存してよいかの最終判断は planCookieRefresh(fail-closed)。
 *
 * ⚠️ ここで例外を投げない。延命に失敗しても入札・同期そのものは続けてよい
 * (失敗したら今までと同じ = 若返らないだけ)。ただし黙って飲まずに必ずログへ出す。
 */
export async function refreshStoredCookies(
  context: BrowserContext,
  yahooSessionId: string,
): Promise<{ saved: boolean; reason: string }> {
  try {
    const session = await prisma.yahooSession.findUnique({ where: { id: yahooSessionId } });
    if (!session || session.status !== "ACTIVE") {
      return { saved: false, reason: "連携が有効ではありません" };
    }
    const stored = JSON.parse(decryptSecret(session.encryptedCookie)) as YahooCookie[];
    const fresh = toYahooCookies(await context.cookies());
    const plan = planCookieRefresh(stored, fresh);
    if (!plan.save) {
      // 「変化なし」は正常。それ以外(認証 Cookie が消えた等)は見えるようにする。
      if (plan.reason !== "変化なし") {
        console.warn(`[cookieRefresh] ${session.label}: 書き戻しません - ${plan.reason}`);
      }
      return { saved: false, reason: plan.reason };
    }
    // status を where に入れて、この間に失効・削除された連携へ書き戻さない。
    const updated = await prisma.yahooSession.updateMany({
      where: { id: yahooSessionId, status: "ACTIVE" },
      data: { encryptedCookie: encryptSecret(JSON.stringify(plan.cookies)) },
    });
    if (updated.count === 0) {
      return { saved: false, reason: "書き戻す直前に連携が失効しました" };
    }
    console.log(`[cookieRefresh] ${session.label}: Cookie ${plan.cookies.length}件を更新しました`);
    return { saved: true, reason: "更新しました" };
  } catch (err) {
    console.error(`[cookieRefresh] ${yahooSessionId} の書き戻しに失敗:`, err);
    return { saved: false, reason: "書き戻しに失敗しました" };
  }
}
