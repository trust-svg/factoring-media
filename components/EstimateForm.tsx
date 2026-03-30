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
      <div className="bg-green-light/30 border border-green rounded-xl p-8 text-center max-w-lg mx-auto">
        <div className="text-4xl mb-4">&#10003;</div>
        <h3 className="text-xl font-bold text-navy mb-2">お見積もり依頼を受け付けました</h3>
        <p className="text-gray-600">
          ご入力いただいたメールアドレス宛に、最適なファクタリング業者の情報をお送りいたします。
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          事業形態 <span className="text-warning">*</span>
        </label>
        <select
          required
          value={formData.businessType}
          onChange={(e) => setFormData({ ...formData, businessType: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-4 py-3"
        >
          <option value="">選択してください</option>
          <option value="法人">法人</option>
          <option value="個人事業主">個人事業主</option>
          <option value="フリーランス">フリーランス</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          請求書金額（万円） <span className="text-warning">*</span>
        </label>
        <input
          type="number"
          required
          min={1}
          value={formData.invoiceAmount}
          onChange={(e) => setFormData({ ...formData, invoiceAmount: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-4 py-3"
          placeholder="例: 500"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          急ぎ度 <span className="text-warning">*</span>
        </label>
        <select
          required
          value={formData.urgency}
          onChange={(e) => setFormData({ ...formData, urgency: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-4 py-3"
        >
          <option value="">選択してください</option>
          <option value="即日">即日（今日中に資金が必要）</option>
          <option value="2-3日以内">2〜3日以内</option>
          <option value="1週間以内">1週間以内</option>
          <option value="急ぎではない">急ぎではない</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          メールアドレス <span className="text-warning">*</span>
        </label>
        <input
          type="email"
          required
          value={formData.email}
          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-4 py-3"
          placeholder="example@company.com"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">電話番号</label>
        <input
          type="tel"
          value={formData.phone}
          onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-4 py-3"
          placeholder="090-1234-5678"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">備考</label>
        <textarea
          rows={3}
          value={formData.memo}
          onChange={(e) => setFormData({ ...formData, memo: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-4 py-3"
          placeholder="その他ご要望があればご記入ください"
        />
      </div>

      {error && <p className="text-warning text-sm">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="w-full bg-green text-white py-4 rounded-xl text-lg font-bold hover:bg-green-dark transition-colors disabled:opacity-50 shadow-lg"
      >
        {submitting ? "送信中..." : "無料で一括見積もりする"}
      </button>

      <p className="text-xs text-gray-400 text-center">
        ※ 個人情報は見積もり目的のみに使用し、第三者に無断で提供することはありません。
      </p>
    </form>
  );
}
