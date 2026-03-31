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
      <div className="bg-green/5 border-2 border-green rounded-xl p-6 text-center">
        <div className="w-12 h-12 bg-green rounded-full flex items-center justify-center mx-auto mb-3">
          <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p className="text-lg font-bold text-primary-darker mb-2">口コミを投稿しました</p>
        <p className="text-sm text-gray-600">
          承認後にサイトに公開されます。ご投稿ありがとうございました。
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="bg-gray-50 border border-gray-200 rounded-xl p-6 space-y-4">
      <h3 className="text-lg font-bold text-primary-darker flex items-center gap-2">
        <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
        {companyName}の口コミを投稿する
      </h3>

      <div>
        <label className="block text-sm font-bold text-gray-700 mb-2">評価</label>
        <div className="flex gap-1.5">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setFormData({ ...formData, rating: n })}
              className="group relative"
            >
              <svg
                className={`w-10 h-10 transition-all ${
                  formData.rating >= n
                    ? "text-star drop-shadow-sm scale-110"
                    : "text-gray-200 hover:text-star/40"
                }`}
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
              </svg>
            </button>
          ))}
          <span className="self-center ml-2 text-sm font-bold text-gray-600">{formData.rating}.0</span>
        </div>
      </div>

      <div>
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          利用者の属性
        </label>
        <select
          value={formData.userType}
          onChange={(e) => setFormData({ ...formData, userType: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
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
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          タイトル <span className="text-cta">*</span>
        </label>
        <input
          type="text"
          required
          maxLength={100}
          value={formData.title}
          onChange={(e) => setFormData({ ...formData, title: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
          placeholder="例：手数料が安くて助かりました"
        />
      </div>

      <div>
        <label className="block text-sm font-bold text-gray-700 mb-1.5">
          口コミ内容 <span className="text-cta">*</span>
        </label>
        <textarea
          required
          rows={4}
          maxLength={2000}
          value={formData.body}
          onChange={(e) => setFormData({ ...formData, body: e.target.value })}
          className="w-full border-2 border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
          placeholder="利用した感想を具体的に教えてください"
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
        className="w-full bg-primary text-white py-3.5 rounded-lg font-bold hover:bg-primary-dark transition-colors disabled:opacity-50 shadow-md"
      >
        {submitting ? "送信中..." : "口コミを投稿する"}
      </button>
    </form>
  );
}
