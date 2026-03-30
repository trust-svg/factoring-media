import { EstimateForm } from "@/components/EstimateForm";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "無料一括見積もり | あなたに最適なファクタリング業者をご紹介",
  description:
    "30秒の簡単入力で、あなたの条件に最適なファクタリング業者を無料でご紹介。手数料・入金速度を比較できます。",
};

export default function EstimatePage() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      <div className="text-center mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-navy mb-3">
          無料一括見積もり
        </h1>
        <p className="text-gray-600">
          30秒の簡単入力で、あなたの条件に最適なファクタリング業者をご紹介します
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-6 md:p-8 shadow-sm">
        <EstimateForm />
      </div>

      <div className="mt-10 grid md:grid-cols-3 gap-4">
        <div className="bg-gray-50 rounded-lg p-4 text-center">
          <div className="text-2xl mb-2">&#128274;</div>
          <h3 className="font-bold text-navy text-sm mb-1">安心のセキュリティ</h3>
          <p className="text-xs text-gray-500">SSL暗号化通信で安全に送信</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-4 text-center">
          <div className="text-2xl mb-2">&#128176;</div>
          <h3 className="font-bold text-navy text-sm mb-1">完全無料</h3>
          <p className="text-xs text-gray-500">見積もり・相談は一切無料です</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-4 text-center">
          <div className="text-2xl mb-2">&#9889;</div>
          <h3 className="font-bold text-navy text-sm mb-1">最短30秒</h3>
          <p className="text-xs text-gray-500">簡単入力ですぐに結果が届きます</p>
        </div>
      </div>
    </div>
  );
}
