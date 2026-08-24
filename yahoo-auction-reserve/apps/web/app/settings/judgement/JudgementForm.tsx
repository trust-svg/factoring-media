"use client";

import { useState } from "react";

export interface JudgementFormValue {
  sellerRatingFloor: string;
  sellerRatingMinCount: string;
  blockLowRatedSeller: boolean;
}

export default function JudgementForm({ initial }: { initial: JudgementFormValue }) {
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const set = <K extends keyof JudgementFormValue>(key: K, v: JudgementFormValue[K]) => {
    setValue((prev) => ({ ...prev, [key]: v }));
    setSaved(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/judgement-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sellerRatingFloor: value.sellerRatingFloor,
          sellerRatingMinCount: value.sellerRatingMinCount,
          blockLowRatedSeller: value.blockLowRatedSeller,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "保存できませんでした");
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="form" onSubmit={submit}>
      <p className="notice">
        空欄にすると、その項目では判定しません。
        出品者の評価が読み取れなかった商品は「不明」として扱い、
        ブロックはしません(読み取りが壊れた日に全部の予約ができなくなるのを避けるため)。
      </p>

      <div>
        <label htmlFor="sellerRatingFloor">「良い」評価の割合の下限 (%)</label>
        <input
          id="sellerRatingFloor"
          type="number"
          min={0}
          max={100}
          value={value.sellerRatingFloor}
          onChange={(e) => set("sellerRatingFloor", e.target.value)}
          placeholder="例: 95"
        />
        <p className="muted">これを下回る出品者は一覧と確認画面で警告します。</p>
      </div>

      <div>
        <label htmlFor="sellerRatingMinCount">評価件数の下限 (件)</label>
        <input
          id="sellerRatingMinCount"
          type="number"
          min={0}
          value={value.sellerRatingMinCount}
          onChange={(e) => set("sellerRatingMinCount", e.target.value)}
          placeholder="例: 20"
        />
        <p className="muted">
          割合だけでは、評価1件で100%の新規出品者と区別がつきません。
        </p>
      </div>

      <label className="check">
        <input
          type="checkbox"
          checked={value.blockLowRatedSeller}
          onChange={(e) => set("blockLowRatedSeller", e.target.checked)}
        />
        条件に該当する出品者の商品は、予約の登録自体を断る
      </label>
      <p className="muted">
        OFF のままなら警告表示だけで、登録はできます。
      </p>

      {error && <p className="error">{error}</p>}
      {saved && <p className="muted">保存しました</p>}
      <button disabled={saving}>{saving ? "保存中…" : "保存"}</button>
    </form>
  );
}
