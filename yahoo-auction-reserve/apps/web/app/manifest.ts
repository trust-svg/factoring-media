import type { MetadataRoute } from "next";

// ホーム画面から起動したときにブラウザ UI を出さない(display: standalone)。
// アイコンは MVP では用意していないので宣言しない。宣言だけして 404 にすると
// インストール自体が拒否される。
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
  };
}
