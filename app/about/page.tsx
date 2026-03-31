import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "運営者情報",
  robots: { index: true, follow: true },
};

export default function AboutPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-2xl font-bold text-gray-900 mb-8">運営者情報</h1>
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <tbody>
            {[
              ["サイト名", "ファクセル（FACCEL）"],
              ["URL", "https://faccel.jp"],
              ["サイト概要", "ファクタリング業者の口コミ・評判を比較し、最適な業者選びをサポートする情報メディア"],
              ["お問い合わせ", "サイト内のお問い合わせフォームよりご連絡ください"],
            ].map(([label, value]) => (
              <tr key={label} className="border-b border-gray-100">
                <th className="px-6 py-4 text-left text-gray-500 bg-gray-50 w-40 font-medium">
                  {label}
                </th>
                <td className="px-6 py-4 text-gray-800">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-8 space-y-6 text-sm text-gray-700 leading-relaxed">
        <h2 className="text-lg font-bold text-gray-900">免責事項</h2>
        <p>
          当サイトに掲載されている情報は、各ファクタリング業者の公式サイトおよび公開情報をもとに編集部が独自に調査・編集したものです。
          情報の正確性には万全を期しておりますが、最新の情報については各業者の公式サイトをご確認ください。
        </p>
        <p>
          当サイトを通じて行われた取引や、情報の利用により生じた損害について、当サイトは一切の責任を負いかねます。
          ファクタリングの利用にあたっては、ご自身の判断と責任において行ってください。
        </p>

        <h2 className="text-lg font-bold text-gray-900">掲載情報について</h2>
        <p>
          当サイトは一部アフィリエイトプログラムに参加しており、掲載業者のリンクを通じて申込みがあった場合、
          当サイトに報酬が支払われることがあります。ただし、ランキングや評価はアフィリエイト報酬の有無に関わらず、
          手数料、入金速度、口コミ評判、サービスの充実度等を独自の基準で総合的に評価しています。
        </p>

        <h2 className="text-lg font-bold text-gray-900">著作権について</h2>
        <p>
          当サイトに掲載されているコンテンツ（文章、画像、デザイン等）の著作権は当サイト運営者に帰属します。
          無断での転載・複製・改変は禁止いたします。
        </p>
      </div>
    </div>
  );
}
