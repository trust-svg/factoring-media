import { chromium, type Browser, type BrowserContext } from "playwright";
import { decryptSecret, type YahooCookie } from "@yar/shared";
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
