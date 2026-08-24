// このリポジトリは親リポジトリ(factoring-media)のサブディレクトリに同居している。
// 親のルートには Tailwind 前提の postcss.config.mjs があり、ここに設定を置かないと
// Next がそれを拾って `Cannot find module '@tailwindcss/postcss'` でビルドが落ちる。
// MVP の globals.css は素の CSS なのでプラグインは空でよい(設計 §5・P1 で Tailwind 導入時に差し替える)。
const config = {
  plugins: {},
};

export default config;
