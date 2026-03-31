"use client";

import { useState } from "react";
import Image from "next/image";

type Result = {
  slug: string;
  name: string;
  fee: string;
  speed: string;
  point: string;
  url: string;
};

const allResults: Record<string, Result[]> = {
  "法人_即日": [
    { slug: "ququmo", name: "QuQuMo", fee: "1%〜14.8%", speed: "最短2時間", point: "買取上限なし・オンライン完結", url: "/companies/ququmo" },
    { slug: "beat-trading", name: "ビートレーディング", fee: "2%〜12%", speed: "最短5時間", point: "累計1,300億円超の実績", url: "/companies/beat-trading" },
    { slug: "accel-factor", name: "アクセルファクター", fee: "2%〜20%", speed: "最短即日", point: "審査通過率93%以上", url: "/companies/accel-factor" },
  ],
  "法人_通常": [
    { slug: "factoru", name: "ファクトル", fee: "1.5%〜10%", speed: "最短即日", point: "非営利法人運営で信頼性◎", url: "/companies/factoru" },
    { slug: "ququmo", name: "QuQuMo", fee: "1%〜14.8%", speed: "最短2時間", point: "手数料1%〜で業界最安級", url: "/companies/ququmo" },
    { slug: "beat-trading", name: "ビートレーディング", fee: "2%〜12%", speed: "最短5時間", point: "2社間・3社間両対応", url: "/companies/beat-trading" },
  ],
  "個人事業主_即日": [
    { slug: "ququmo", name: "QuQuMo", fee: "1%〜14.8%", speed: "最短2時間", point: "個人事業主OK・上限なし", url: "/companies/ququmo" },
    { slug: "accel-factor", name: "アクセルファクター", fee: "2%〜20%", speed: "最短即日", point: "審査通過率93%・少額OK", url: "/companies/accel-factor" },
    { slug: "paytoday", name: "ペイトナー", fee: "一律10%", speed: "最短10分", point: "最短10分で審査完了", url: "/companies/paytoday" },
  ],
  "個人事業主_通常": [
    { slug: "factoru", name: "ファクトル", fee: "1.5%〜10%", speed: "最短即日", point: "非営利法人の安心感", url: "/companies/factoru" },
    { slug: "ququmo", name: "QuQuMo", fee: "1%〜14.8%", speed: "最短2時間", point: "手数料1%〜", url: "/companies/ququmo" },
    { slug: "beat-trading", name: "ビートレーディング", fee: "2%〜12%", speed: "最短5時間", point: "実績1,300億円超", url: "/companies/beat-trading" },
  ],
  "フリーランス_即日": [
    { slug: "paytoday", name: "ペイトナー", fee: "一律10%", speed: "最短10分", point: "請求書1枚・最短10分", url: "/companies/paytoday" },
    { slug: "labol", name: "ラボル", fee: "一律10%", speed: "最短60分", point: "1万円から・上場企業G", url: "/companies/labol" },
    { slug: "ququmo", name: "QuQuMo", fee: "1%〜14.8%", speed: "最短2時間", point: "大口にも対応可能", url: "/companies/ququmo" },
  ],
  "フリーランス_通常": [
    { slug: "paytoday", name: "ペイトナー", fee: "一律10%", speed: "最短10分", point: "フリーランス特化No.1", url: "/companies/paytoday" },
    { slug: "labol", name: "ラボル", fee: "一律10%", speed: "最短60分", point: "24時間365日対応", url: "/companies/labol" },
    { slug: "factoru", name: "ファクトル", fee: "1.5%〜10%", speed: "最短即日", point: "手数料を抑えたい方に", url: "/companies/factoru" },
  ],
};

function getResults(businessType: string, urgency: string): Result[] {
  const isUrgent = urgency === "即日" || urgency === "2-3日以内";
  const key = `${businessType}_${isUrgent ? "即日" : "通常"}`;
  return allResults[key] || allResults["法人_通常"];
}

export function EstimateForm() {
  const [step, setStep] = useState(1);
  const [businessType, setBusinessType] = useState("");
  const [amount, setAmount] = useState("");
  const [urgency, setUrgency] = useState("");
  const [results, setResults] = useState<Result[] | null>(null);

  const handleDiagnose = () => {
    setResults(getResults(businessType, urgency));
    setStep(4);
  };

  if (results) {
    return (
      <div className="space-y-6">
        <div className="text-center">
          <div className="w-16 h-16 bg-primary rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-gray-900 mb-1">診断結果</h3>
          <p className="text-gray-500">
            {businessType}・{amount ? `${amount}万円` : ""}・{urgency}
          </p>
        </div>

        <div className="flex gap-3 items-start bg-primary/5 border border-primary/10 rounded-xl p-4">
          <div className="w-10 h-10 rounded-full overflow-hidden shrink-0 border-2 border-primary/20">
            <Image src="/images/advisor-sanada-main.png" alt="真田" width={40} height={40} className="object-cover" />
          </div>
          <div>
            <p className="text-xs font-bold text-primary mb-1">アドバイザー 真田</p>
            <p className="text-sm text-gray-700">
              {businessType === "フリーランス"
                ? "フリーランスの方には少額対応・オンライン完結の業者がおすすめです。以下の3社を比較してみてください。"
                : urgency === "即日"
                ? "即日入金をご希望ですね。スピード重視の3社をピックアップしました。午前中の申込みで当日入金の可能性が高まります。"
                : "条件に合う3社を厳選しました。手数料と入金スピードのバランスが良い業者です。複数社に相談して比較することをおすすめします。"}
            </p>
          </div>
        </div>

        <div className="space-y-3">
          {results.map((r, i) => (
            <div key={r.slug} className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="flex items-center gap-3 mb-3">
                <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-black ${
                  i === 0 ? "bg-amber-400 text-amber-900" :
                  i === 1 ? "bg-gray-300 text-gray-700" :
                  "bg-amber-600 text-white"
                }`}>{i + 1}</span>
                <h4 className="font-bold text-gray-900">{r.name}</h4>
                <span className="text-xs text-primary bg-primary/5 px-2 py-0.5 rounded-full ml-auto">{r.point}</span>
              </div>
              <div className="flex gap-4 mb-3">
                <div>
                  <span className="text-xs text-gray-400 block">手数料</span>
                  <span className="font-bold text-primary">{r.fee}</span>
                </div>
                <div>
                  <span className="text-xs text-gray-400 block">入金速度</span>
                  <span className="font-bold text-secondary">{r.speed}</span>
                </div>
              </div>
              <div className="flex gap-2">
                <a
                  href={r.url}
                  className="flex-1 text-center text-sm border-2 border-primary text-primary py-2.5 rounded-lg font-bold hover:bg-primary hover:text-white transition-colors"
                >
                  詳細・口コミ
                </a>
                <a
                  href={r.url}
                  className="flex-1 text-center text-sm bg-cta text-white py-2.5 rounded-lg font-bold hover:bg-cta-dark transition-colors shadow-md"
                >
                  公式サイトへ →
                </a>
              </div>
            </div>
          ))}
        </div>

        <button
          onClick={() => { setResults(null); setStep(1); setBusinessType(""); setAmount(""); setUrgency(""); }}
          className="w-full text-center text-sm text-gray-400 hover:text-gray-600 py-2"
        >
          もう一度診断する
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Progress bar */}
      <div className="flex gap-1">
        {[1, 2, 3].map((s) => (
          <div key={s} className={`h-1.5 flex-1 rounded-full ${step >= s ? "bg-primary" : "bg-gray-200"}`} />
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-4">
          <h3 className="text-lg font-bold text-gray-900 text-center">事業形態を選択</h3>
          <div className="grid grid-cols-1 gap-3">
            {["法人", "個人事業主", "フリーランス"].map((type) => (
              <button
                key={type}
                onClick={() => { setBusinessType(type); setStep(2); }}
                className="w-full text-left px-5 py-4 border-2 border-gray-200 rounded-xl hover:border-primary hover:bg-primary/5 transition-all font-bold text-gray-700"
              >
                {type}
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <h3 className="text-lg font-bold text-gray-900 text-center">請求書金額は？</h3>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "〜50万円", value: "50" },
              { label: "50〜100万円", value: "100" },
              { label: "100〜500万円", value: "500" },
              { label: "500万円〜", value: "1000" },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => { setAmount(opt.value); setStep(3); }}
                className="px-4 py-4 border-2 border-gray-200 rounded-xl hover:border-primary hover:bg-primary/5 transition-all font-bold text-gray-700 text-center"
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button onClick={() => setStep(1)} className="text-sm text-gray-400 hover:text-gray-600">← 戻る</button>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <h3 className="text-lg font-bold text-gray-900 text-center">急ぎ度は？</h3>
          <div className="grid grid-cols-1 gap-3">
            {[
              { label: "即日（今日中に必要）", value: "即日" },
              { label: "2〜3日以内", value: "2-3日以内" },
              { label: "1週間以内", value: "1週間以内" },
              { label: "急ぎではない", value: "急ぎではない" },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => { setUrgency(opt.value); handleDiagnose(); }}
                className="w-full text-left px-5 py-4 border-2 border-gray-200 rounded-xl hover:border-primary hover:bg-primary/5 transition-all font-bold text-gray-700"
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button onClick={() => setStep(2)} className="text-sm text-gray-400 hover:text-gray-600">← 戻る</button>
        </div>
      )}
    </div>
  );
}
