import type { YahooCookie } from "./types";
import { YAHOO_AUTH_COOKIE_NAMES } from "./cookies";

// =============================================================
// 連携 Cookie の書き戻し(セッション延命)
//
// なぜ要るか(2026-09-21 の失効の根本原因):
//   Cookie の保存は **登録時の1回だけ** だった。入札・監視・ウォッチリスト
//   同期はどれも登録時のスナップショットを注入するだけで、ヤフオクが返した
//   更新後の Cookie を読み戻していなかった。普通のブラウザなら使うたびに
//   若返る Cookie が、このアプリでは登録した日のまま歳を取り続ける。
//   2026-08-24 に登録した連携は約4週間で失効し、**入札の瞬間** に
//   SESSION_EXPIRED になって予約1件(r1244958094)を落とし損ねた。
//
// ⚠️ 書き戻しは **fail-closed**。ログアウト後や取得失敗のときの一式を
//   そのまま保存すると、生きているスナップショットを自分で潰して
//   「再連携したのに翌日また切れる」形の故障になる。保存してよいと
//   言い切れるときだけ save する。
//
// ⚠️ この関数は「延命」であって「復活」ではない。ヤフオク側の絶対寿命は
//   越えられないので、切れたら人手の再連携が要るのは変わらない。
// =============================================================

export type CookieRefreshPlan =
  | { save: true; cookies: YahooCookie[] }
  | { save: false; reason: string };

/**
 * ブラウザから取り出した最新 Cookie を保管し直してよいかを決める。
 *
 * @param stored 現在 DB に入っている一式(復号済み)
 * @param fresh  `context.cookies()` で取り出した一式
 */
export function planCookieRefresh(
  stored: YahooCookie[],
  fresh: YahooCookie[],
): CookieRefreshPlan {
  // 他サイトのセッションは預からない(登録時の normalizeYahooCookies と同じ方針)
  const next = fresh.filter((c) => isYahooDomain(c.domain));
  if (next.length === 0) {
    return { save: false, reason: "yahoo.co.jp の Cookie が1件も取れませんでした" };
  }

  // 保管済みに在った認証 Cookie が消えていたら、それはログアウトか取得失敗。
  // 「元から無かった」ものは欠けていても異常ではないので stored を基準にする。
  const had = new Set(stored.filter((c) => hasValue(c)).map((c) => c.name));
  const nowHas = new Set(next.filter((c) => hasValue(c)).map((c) => c.name));
  const lost = YAHOO_AUTH_COOKIE_NAMES.filter((n) => had.has(n) && !nowHas.has(n));
  if (lost.length > 0) {
    return {
      save: false,
      reason: `認証 Cookie (${lost.join(", ")}) が取得結果から消えています`,
    };
  }

  // 変わっていないなら書かない。書くと updatedAt だけが動き、
  // 「最後に更新された時刻」が延命の証跡として使えなくなる。
  if (fingerprint(stored) === fingerprint(next)) {
    return { save: false, reason: "変化なし" };
  }

  return { save: true, cookies: next };
}

function isYahooDomain(domain: string): boolean {
  return domain.replace(/^\./, "").endsWith("yahoo.co.jp");
}

function hasValue(c: YahooCookie): boolean {
  return c.value.length > 0;
}

// 並び順はブラウザ都合で変わるので、比較の前に正規化して並べ直す。
//
// ⚠️ 省略値は **注入側と同じ既定値** に寄せてから比べる(session.ts の
//    addCookies と揃える)。揃えないと、登録時に省略された属性と
//    ブラウザが明示で返す属性が毎回「差分あり」になり、「変化なし」の
//    判定が永久に効かず1時間ごとに無駄な書き込みが走る。
function fingerprint(cookies: YahooCookie[]): string {
  return cookies
    .map((c) =>
      [
        c.name,
        c.value,
        c.domain,
        c.path ?? "/",
        c.expires ?? "",
        c.httpOnly ?? false,
        c.secure ?? true,
        c.sameSite ?? "",
      ].join("\u0000"),
    )
    .sort()
    .join("\u0001");
}

/** Playwright の `context.cookies()` が返す1件 */
export interface PlaywrightCookie {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires: number;
  httpOnly: boolean;
  secure: boolean;
  sameSite?: "Strict" | "Lax" | "None";
}

/**
 * Playwright の Cookie を保管形式へ直す。
 *
 * ⚠️ Playwright はセッション Cookie の `expires` を **-1** で返す。保管側は
 *    「省略 = セッション Cookie」なので、-1 のまま入れると登録時の一式と
 *    毎回差分が出る(= 変化していないのに毎回書き戻す)。ここで落とす。
 */
export function toYahooCookies(raw: PlaywrightCookie[]): YahooCookie[] {
  return raw.map((c) => {
    const cookie: YahooCookie = {
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      httpOnly: c.httpOnly,
      secure: c.secure,
    };
    if (Number.isFinite(c.expires) && c.expires > 0) cookie.expires = Math.floor(c.expires);
    if (c.sameSite === "Strict" || c.sameSite === "Lax" || c.sameSite === "None") {
      cookie.sameSite = c.sameSite;
    }
    return cookie;
  });
}
