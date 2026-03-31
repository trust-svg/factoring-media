import { EstimateForm } from "@/components/EstimateForm";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "無料診断 | あなたに最適なファクタリング業者を30秒で診断",
  description:
    "3つの質問に答えるだけで、あなたの条件に最適なファクタリング業者がすぐにわかります。個人情報の入力不要。",
};

export default function EstimatePage() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      <div className="text-center mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-3">
          あなたに最適な業者を無料診断
        </h1>
        <p className="text-gray-600">
          3つの質問に答えるだけ。個人情報の入力は不要です。
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-6 md:p-8 shadow-sm">
        <EstimateForm />
      </div>

      <div className="mt-10 grid md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-100 p-4 text-center">
          <svg className="w-8 h-8 text-primary mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <h3 className="font-bold text-gray-900 text-sm mb-1">個人情報不要</h3>
          <p className="text-xs text-gray-500">メールアドレスや電話番号の入力は不要です</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-100 p-4 text-center">
          <svg className="w-8 h-8 text-primary mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <h3 className="font-bold text-gray-900 text-sm mb-1">最短30秒</h3>
          <p className="text-xs text-gray-500">3つの質問に答えるだけですぐに結果が表示</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-100 p-4 text-center">
          <svg className="w-8 h-8 text-primary mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <h3 className="font-bold text-gray-900 text-sm mb-1">厳選業者のみ</h3>
          <p className="text-xs text-gray-500">手数料・実績を基に厳選した優良業者をご紹介</p>
        </div>
      </div>
    </div>
  );
}
