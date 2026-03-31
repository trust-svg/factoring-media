"use client";

import { useState } from "react";

export function EstimateForm() {
  const [formData, setFormData] = useState({
    businessType: "",
    invoiceAmount: "",
    urgency: "",
    email: "",
    phone: "",
    memo: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const res = await fetch("/api/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...formData,
          invoiceAmount: parseInt(formData.invoiceAmount),
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "送信に失敗しました");
      }

      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="bg-green/5 border-2 border-green rounded-xl p-8 text-center max-w-lg mx-auto">
        <div className="w-16 h-16 bg-green rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h3 className="text-xl font-bold text-primary-darker mb-2">お見積もり依頼を受け付けました</h3>
        <p className="text-gray-600">
          ご入力いただいたメールアドレス宛に、最適なファクタリング業者の情報をお送りいたします。
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          <span className="flex items-center gap-1">
            <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            事業形態 <span className="text-cta">*</span>
          </span>
        </label>
        <select
          required
          value={formData.businessType}
          onChange={(e) => setFormData({ ...formData, businessType: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-4 py-3 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
        >
          <option value="">選択してください</option>
          <option value="法人">法人</option>
          <option value="個人事業主">個人事業主</option>
          <option value="フリーランス">フリーランス</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          <span className="flex items-center gap-1">
            <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            請求書金額（万円） <span className="text-cta">*</span>
          </span>
        </label>
        <input
          type="number"
          required
          min={1}
          value={formData.invoiceAmount}
          onChange={(e) => setFormData({ ...formData, invoiceAmount: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-4 py-3 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
          placeholder="例: 500"
        />
      </div>

      <div>
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          <span className="flex items-center gap-1">
            <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            急ぎ度 <span className="text-cta">*</span>
          </span>
        </label>
        <select
          required
          value={formData.urgency}
          onChange={(e) => setFormData({ ...formData, urgency: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-4 py-3 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
        >
          <option value="">選択してください</option>
          <option value="即日">即日（今日中に資金が必要）</option>
          <option value="2-3日以内">2〜3日以内</option>
          <option value="1週間以内">1週間以内</option>
          <option value="急ぎではない">急ぎではない</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          <span className="flex items-center gap-1">
            <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            メールアドレス <span className="text-cta">*</span>
          </span>
        </label>
        <input
          type="email"
          required
          value={formData.email}
          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-4 py-3 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
          placeholder="example@company.com"
        />
      </div>

      <div>
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          <span className="flex items-center gap-1">
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
            電話番号
          </span>
        </label>
        <input
          type="tel"
          value={formData.phone}
          onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-4 py-3 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
          placeholder="090-1234-5678"
        />
      </div>

      <div>
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          <span className="flex items-center gap-1">
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            備考
          </span>
        </label>
        <textarea
          rows={3}
          value={formData.memo}
          onChange={(e) => setFormData({ ...formData, memo: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-4 py-3 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
          placeholder="その他ご要望があればご記入ください"
        />
      </div>

      {error && (
        <div className="bg-cta/5 border border-cta/20 rounded-lg px-4 py-3 flex items-center gap-2">
          <svg className="w-4 h-4 text-cta shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-cta text-sm">{error}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="w-full bg-cta text-white py-4 rounded-xl text-lg font-bold hover:bg-cta-dark transition-colors disabled:opacity-50 shadow-lg pulse-cta"
      >
        {submitting ? "送信中..." : "無料で一括見積もりする"}
      </button>

      <p className="text-xs text-gray-400 text-center flex items-center justify-center gap-1">
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        個人情報は見積もり目的のみに使用し、第三者に無断で提供することはありません。
      </p>
    </form>
  );
}
