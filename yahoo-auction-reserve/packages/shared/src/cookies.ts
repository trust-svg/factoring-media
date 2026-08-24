import type { YahooCookie } from "./types";

// =============================================================
// ブラウザから持ち込まれた Cookie の正規化
//
// 実運用では次のいずれかの形で貼り付けられる想定:
//   1. Cookie-Editor / EditThisCookie の JSON エクスポート(配列)
//      → expirationDate(秒・小数) / sameSite が "no_restriction" 等
//   2. Playwright の storageState ({ cookies: [...] })
//   3. 素の配列(このアプリの YahooCookie 形式そのまま)
//
// Playwright の addCookies は sameSite が "Strict"|"Lax"|"None" 以外だと
// 実行時に例外を投げる。ここで弾いておかないと「登録は成功したのに
// 入札の瞬間だけ落ちる」形の故障になるため、投入前に必ず通す。
// =============================================================

// Yahoo! JAPAN のログイン状態に必要とされる代表的な Cookie 名。
// ※ 実際に必要な組み合わせは P0 検証(設計 §13)で確定させること。
export const YAHOO_AUTH_COOKIE_NAMES = ["T", "Y", "SSL", "SSLK"] as const;

export interface NormalizedCookies {
  cookies: YahooCookie[];
  warnings: string[];
}

export class CookieParseError extends Error {}

export function parseCookieInput(input: string): unknown {
  let parsed: unknown;
  try {
    parsed = JSON.parse(input);
  } catch {
    throw new CookieParseError("JSON として読み取れませんでした");
  }
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const inner = (parsed as { cookies?: unknown }).cookies;
    if (Array.isArray(inner)) return inner;
  }
  return parsed;
}

export function normalizeYahooCookies(raw: unknown): NormalizedCookies {
  if (!Array.isArray(raw) || raw.length === 0) {
    throw new CookieParseError("Cookie の配列が空です");
  }

  const cookies: YahooCookie[] = [];
  const skipped: string[] = [];

  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const c = item as Record<string, unknown>;
    const name = typeof c.name === "string" ? c.name : null;
    const value = typeof c.value === "string" ? c.value : null;
    const domain = typeof c.domain === "string" ? c.domain : null;
    if (!name || value === null || !domain) continue;

    // yahoo.co.jp 以外は保存しない(他サイトのセッションを預からない)
    if (!domain.replace(/^\./, "").endsWith("yahoo.co.jp")) {
      skipped.push(domain);
      continue;
    }

    const cookie: YahooCookie = {
      name,
      value,
      domain,
      path: typeof c.path === "string" ? c.path : "/",
      secure: typeof c.secure === "boolean" ? c.secure : true,
    };
    if (typeof c.httpOnly === "boolean") cookie.httpOnly = c.httpOnly;

    const expires = toExpiresSeconds(c);
    if (expires !== undefined) cookie.expires = expires;

    const sameSite = toSameSite(c.sameSite);
    if (sameSite) cookie.sameSite = sameSite;

    cookies.push(cookie);
  }

  if (cookies.length === 0) {
    throw new CookieParseError(
      "yahoo.co.jp ドメインの Cookie が1件も含まれていません",
    );
  }

  const warnings: string[] = [];
  const names = new Set(cookies.map((c) => c.name));
  const missing = YAHOO_AUTH_COOKIE_NAMES.filter((n) => !names.has(n));
  if (missing.length > 0) {
    warnings.push(
      `ログインに必要とみられる Cookie (${missing.join(", ")}) が含まれていません。` +
        "ヤフオクにログインした状態で、httpOnly を含む Cookie をすべてエクスポートしてください。",
    );
  }
  if (skipped.length > 0) {
    warnings.push(
      `yahoo.co.jp 以外のドメイン(${[...new Set(skipped)].join(", ")})の Cookie は保存しませんでした。`,
    );
  }
  return { cookies, warnings };
}

// Cookie-Editor は expirationDate(UNIX秒・小数)、Playwright は expires(秒)
function toExpiresSeconds(c: Record<string, unknown>): number | undefined {
  const raw = c.expires ?? c.expirationDate;
  if (typeof raw !== "number" || !Number.isFinite(raw)) return undefined;
  if (raw <= 0) return undefined; // セッションCookie
  // ミリ秒で入っている実装もあるので秒に寄せる
  const seconds = raw > 1e11 ? raw / 1000 : raw;
  return Math.floor(seconds);
}

function toSameSite(raw: unknown): YahooCookie["sameSite"] | undefined {
  if (typeof raw !== "string") return undefined;
  switch (raw.toLowerCase()) {
    case "strict":
      return "Strict";
    case "lax":
      return "Lax";
    case "none":
    case "no_restriction":
      return "None";
    default:
      // "unspecified" 等は Playwright が受け付けないので付けない
      return undefined;
  }
}
