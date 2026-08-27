import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

/**
 * ルートは入口の振り分けだけ。ログイン済みならダッシュボード、でなければログイン。
 *
 * ⚠️ ここには以前サービス紹介のランディングページ(「無料で始める」→ /register)が
 *    置いてあった。設計初期の不特定多数向けの想定が残っていたもので、
 *    実際の運用(単一利用者・tailnet 内からのみ到達可)とは合わなくなっていた。
 *    その結果、URL を開くと **登録画面へ誘導されるのに登録は閉じている**
 *    (packages/shared/src/access.ts: 利用者が0人のときだけ開く)という
 *    行き止まりになっていた。
 *
 *    しかも残っていた紹介文は3点とも実装と食い違っていた:
 *      - 「電源OFFでもサーバー側で実行されます」→ 実際は Mac 上で動く。
 *        ヤフオクがデータセンター IP を弾くので VPS に載せられない(設計 §4)。
 *        スリープすれば実行されない
 *      - 「メールで通知」→ 実際は Telegram
 *      - 「5〜300秒前」→ 実際の上限は SNIPE_SECONDS_MAX = 600
 *    紹介文は動作に影響しないぶん誰も直さないまま残る。置かないのが一番安い。
 */
export default async function RootPage() {
  const user = await getSessionUser();
  redirect(user ? "/dashboard" : "/login");
}
