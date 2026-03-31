import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "利用規約",
};

export default function TermsPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-2xl font-bold text-gray-900 mb-8">利用規約</h1>
      <div className="space-y-8 text-sm text-gray-700 leading-relaxed">
        <p>
          本利用規約（以下「本規約」）は、ファクセル（以下「当サイト」）の利用条件を定めるものです。
          当サイトをご利用いただく場合、本規約に同意したものとみなします。
        </p>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">第1条（適用範囲）</h2>
          <p>本規約は、当サイトが提供するすべてのサービス（情報提供、口コミ掲載、無料診断等）に適用されます。</p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">第2条（禁止事項）</h2>
          <p>当サイトの利用にあたり、以下の行為を禁止します。</p>
          <ul className="list-disc pl-6 mt-2 space-y-1">
            <li>虚偽の情報を投稿する行為</li>
            <li>他者を誹謗中傷する口コミの投稿</li>
            <li>当サイトのコンテンツを無断で転載・複製する行為</li>
            <li>当サイトの運営を妨害する行為</li>
            <li>法令または公序良俗に違反する行為</li>
            <li>その他、当サイト運営者が不適切と判断する行為</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">第3条（口コミ投稿について）</h2>
          <p>
            ユーザーが投稿した口コミは、当サイト運営者の審査を経て掲載されます。
            投稿内容が本規約に違反すると判断した場合、事前の通知なく削除することがあります。
            投稿された口コミの著作権は投稿者に帰属しますが、当サイトにおける掲載・編集の権利を当サイト運営者に許諾するものとします。
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">第4条（免責事項）</h2>
          <p>
            当サイトに掲載されている情報の正確性、完全性、有用性等について、当サイトは保証するものではありません。
            当サイトを通じて得た情報に基づいて行った判断や行動により生じた損害について、当サイトは一切の責任を負いません。
            ファクタリングの利用は、利用者ご自身の判断と責任において行ってください。
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">第5条（リンクについて）</h2>
          <p>
            当サイトには外部サイトへのリンクが含まれています。リンク先のサイトにおける個人情報の取り扱いやコンテンツについて、
            当サイトは一切の責任を負いません。
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-gray-900 mb-3">第6条（規約の変更）</h2>
          <p>
            当サイトは、必要に応じて本規約を変更することがあります。
            変更後の規約は、当サイトに掲載した時点で効力を生じるものとします。
          </p>
        </section>

        <p className="text-gray-500 pt-4 border-t border-gray-200">
          制定日: 2026年3月31日
        </p>
      </div>
    </div>
  );
}
