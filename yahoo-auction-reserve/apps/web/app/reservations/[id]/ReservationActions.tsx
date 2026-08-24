"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

// 変更・キャンセルは SCHEDULED のときだけ(設計 §9)。
// 実行系との競合を避けるため最終判断はサーバ側が行い、
// ここでの制御はあくまで UI 上の目安。
export default function ReservationActions({
  id,
  editable,
  maxBidAmount,
  snipeSecondsBefore,
}: {
  id: string;
  editable: boolean;
  maxBidAmount: number;
  snipeSecondsBefore: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [amount, setAmount] = useState(String(maxBidAmount));
  const [seconds, setSeconds] = useState(String(snipeSecondsBefore));

  if (!editable) {
    return (
      <div className="card">
        <h2>変更・キャンセル</h2>
        <p className="muted">
          実行が始まっている(または終了している)ため、変更・キャンセルはできません。
        </p>
      </div>
    );
  }

  async function onPatch(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await fetch(`/api/v1/reservations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        maxBidAmount: Number(amount),
        snipeSecondsBefore: Number(seconds),
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError((await res.json()).error ?? "変更に失敗しました");
      return;
    }
    setNotice("変更を保存しました");
    router.refresh();
  }

  async function onCancel() {
    if (!confirm("この予約をキャンセルします。よろしいですか?")) return;
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/v1/reservations/${id}`, { method: "DELETE" });
    setBusy(false);
    if (!res.ok) {
      setError((await res.json()).error ?? "キャンセルに失敗しました");
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <div className="card">
      <h2>変更・キャンセル</h2>
      <form className="form" onSubmit={onPatch}>
        <div>
          <label htmlFor="amount">上限入札額(円)</label>
          <input
            id="amount"
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="seconds">実行タイミング(終了何秒前)</label>
          <input
            id="seconds"
            type="number"
            value={seconds}
            onChange={(e) => setSeconds(e.target.value)}
          />
        </div>
        {error && <p className="error">{error}</p>}
        {notice && <p className="muted">{notice}</p>}
        <div className="row">
          <button disabled={busy}>変更を保存</button>
          <button
            type="button"
            className="danger"
            disabled={busy}
            onClick={onCancel}
          >
            予約をキャンセル
          </button>
        </div>
      </form>
    </div>
  );
}
