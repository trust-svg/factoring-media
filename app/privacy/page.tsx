import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "プライバシーポリシー",
};

export default function PrivacyPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-2xl font-bold text-gray-900 mb-8">プライバシーポリシー</h1>
      <div className="space-y-8 text-sm text-gray-700 leading-relaxed">
        <p>
          ファクセル（以下「当サイト」）は、ユーザーの個人情報の取り扱いについて、以下のとおりプライバシーポリシーを定めます。
        </p>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">1. 収集する情報</h2>
          <p>当サイトでは、以下の情報を収集することがあります。</p>
          <ul className="list-disc pl-6 mt-2 space-y-1">
            <li>無料診断フォームに入力された情報（事業形態、請求書金額、メールアドレス、電話番号等）</li>
            <li>口コミ投稿に含まれる情報（評価、投稿内容、利用者属性）</li>
            <li>アクセスログ（IPアドレス、ブラウザ情報、閲覧ページ等）</li>
            <li>Cookie情報</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">2. 情報の利用目的</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>無料診断サービスの提供および最適な業者のご紹介</li>
            <li>口コミ情報の掲載およびサイトコンテンツの充実</li>
            <li>サイトの改善およびユーザー体験の向上</li>
            <li>アクセス解析によるサイト運営の最適化</li>
            <li>お問い合わせへの対応</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">3. 第三者への提供</h2>
          <p>
            当サイトは、以下の場合を除き、収集した個人情報を第三者に提供することはありません。
          </p>
          <ul className="list-disc pl-6 mt-2 space-y-1">
            <li>ユーザーの同意がある場合</li>
            <li>法令に基づく場合</li>
            <li>無料診断サービスにおいて、提携ファクタリング業者に診断依頼を送信する場合</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">4. アクセス解析ツール</h2>
          <p>
            当サイトでは、Googleアナリティクスを利用してアクセス情報を収集しています。
            Googleアナリティクスはトラフィックデータの収集のためにCookieを使用しています。
            このトラフィックデータは匿名で収集されており、個人を特定するものではありません。
            Cookieを無効にすることで収集を拒否することができます。
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">5. Cookieについて</h2>
          <p>
            当サイトでは、ユーザー体験の向上やアクセス解析のためにCookieを使用しています。
            ブラウザの設定によりCookieを無効にすることが可能ですが、一部のサービスが利用できなくなる場合があります。
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">6. プライバシーポリシーの変更</h2>
          <p>
            当サイトは、必要に応じて本プライバシーポリシーを変更することがあります。
            変更後のプライバシーポリシーは、当サイトに掲載した時点で効力を生じるものとします。
          </p>
        </section>

        <p className="text-gray-500 pt-4 border-t border-gray-200">
          制定日: 2026年3月31日
        </p>
      </div>
    </div>
  );
}
