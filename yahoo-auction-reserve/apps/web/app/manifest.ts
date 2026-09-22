import type { MetadataRoute } from "next";

// ホーム画面から起動したときにブラウザ UI を出さない(display: standalone)。
//
// ⚠️ icons は **実在するファイル** だけを書く。宣言だけして 404 にすると
// インストール自体が拒否される(アイコンを用意する前はここを空にしていた)。
// 実体は apps/web/public/icons/。iOS のホーム画面はこの manifest ではなく
// app/apple-icon.png を見る(そちらは透明を黒く塗られるので下地を敷いてある)。
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ヤフオク入札予約",
    short_name: "入札予約",
    description: "オークション終了直前に自動入札(スナイプ入札)を実行する予約サービス",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#eceff2",
    theme_color: "#eceff2",
    lang: "ja",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
