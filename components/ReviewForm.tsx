"use client";

import { useState } from "react";

export function ReviewForm({ companyId, companyName }: { companyId: number; companyName: string }) {
  const [formData, setFormData] = useState({
    rating: 5,
    title: "",
    body: "",
    userType: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const res = await fetch("/api/reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...formData, companyId }),
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
      <div className="bg-green-light/30 border border-green rounded-xl p-6 text-center">
        <p className="text-lg font-bold text-navy mb-2">口コミを投稿しました</p>
        <p className="text-sm text-gray-600">
          承認後にサイトに公開されます。ご投稿ありがとうございました。
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="bg-gray-50 rounded-xl p-6 space-y-4">
      <h3 className="text-lg font-bold text-navy">
        {companyName}の口コミを投稿する
      </h3>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">評価</label>
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setFormData({ ...formData, rating: n })}
              className={`w-10 h-10 rounded-lg font-bold text-lg transition-colors ${
                formData.rating >= n
                  ? "bg-star text-white"
                  : "bg-gray-200 text-gray-400"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          利用者の属性
        </label>
        <select
          value={formData.userType}
          onChange={(e) => setFormData({ ...formData, userType: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">選択してください</option>
          <option value="個人事業主">個人事業主</option>
          <option value="法人（小規模）">法人（小規模）</option>
          <option value="法人（中規模）">法人（中規模）</option>
          <option value="フリーランス">フリーランス</option>
          <option value="その他">その他</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          タイトル <span className="text-warning">*</span>
        </label>
        <input
          type="text"
          required
          maxLength={100}
          value={formData.title}
          onChange={(e) => setFormData({ ...formData, title: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          placeholder="例：手数料が安くて助かりました"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          口コミ内容 <span className="text-warning">*</span>
        </label>
        <textarea
          required
          rows={4}
          maxLength={2000}
          value={formData.body}
          onChange={(e) => setFormData({ ...formData, body: e.target.value })}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          placeholder="利用した感想を具体的に教えてください"
        />
      </div>

      {error && <p className="text-warning text-sm">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="w-full bg-navy text-white py-3 rounded-lg font-bold hover:bg-navy-light transition-colors disabled:opacity-50"
      >
        {submitting ? "送信中..." : "口コミを投稿する"}
      </button>
    </form>
  );
}
