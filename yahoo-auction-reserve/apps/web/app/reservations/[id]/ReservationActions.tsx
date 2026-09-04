"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

// 変更・キャンセルは SCHEDULED のときだけ(設計 §9)。
// 実行系との競合を避けるため最終判断はサーバ側が行い、
// ここでの制御はあくまで UI 上の目安。
export default function ReservationActions({
  id,
  editable,
  running,
  currentPrice,
  maxBidAmount,
  snipeSecondsBefore,
  dryRun: initialDryRun,
}: {
  id: string;
  editable: boolean;
  /** 走行中(監視中・入札中)で、まだ終了していない = 上限額の引き上げだけ可能 */
  running: boolean;
  currentPrice: number | null;
  maxBidAmount: number;
  snipeSecondsBefore: number;
  dryRun: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [amount, setAmount] = useState(String(maxBidAmount));
  const [seconds, setSeconds] = useState(String(snipeSecondsBefore));
  const [dryRun, setDryRun] = useState(initialDryRun);
  // 引き上げ後の額の初期値。現在価格が分かっていればそれを上回る額から始める。
  const [raiseAmount, setRaiseAmount] = useState(
    String(Math.max(maxBidAmount, currentPrice ?? 0) + 1000),
  );

  async function onRaise(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    // ⚠️ maxBidAmount **だけ** を送る。走行中のサーバ側は他のキーが1つでも
    // 混ざると 409 で弾く(走っているループの前提と食い違うため)。
    const res = await fetch(`/api/v1/reservations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ maxBidAmount: Number(raiseAmount) }),
    });
    setBusy(false);
    if (!res.ok) {
      setError((await res.json()).error ?? "引き上げに失敗しました");
      return;
    }
    setNotice("上限額を引き上げました。次の入札タイミングで再入札します。");
    router.refresh();
  }

  if (!editable && running) {
    return (
      <div className="card">
        <h2>上限額を上げて再入札</h2>
        <p className="muted">
          実行中の予約です。変更できるのは上限額の引き上げだけです
          (実行タイミング・テスト実行・キャンセルはできません)。
          引き上げると、終了{snipeSecondsBefore}秒前の入札タイミングで
          同じ予約のまま入札しなおします。
        </p>
        <form className="form" onSubmit={onRaise}>
          <div>
            <label htmlFor="raiseAmount">
              新しい上限入札額(円) — 現在の上限 ¥{maxBidAmount.toLocaleString("ja-JP")}
              {currentPrice !== null && ` / 現在価格 ¥${currentPrice.toLocaleString("ja-JP")}`}
            </label>
            <input
              id="raiseAmount"
              type="number"
              value={raiseAmount}
              onChange={(e) => setRaiseAmount(e.target.value)}
            />
          </div>
          {error && <p className="error">{error}</p>}
          {notice && <p className="muted">{notice}</p>}
          <div className="row">
            <button disabled={busy}>上限額を引き上げる</button>
          </div>
        </form>
      </div>
    );
  }

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
        dryRun,
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
          <div>
            <label
              htmlFor="dryRun"
              style={{ display: "flex", alignItems: "center", gap: 8 }}
            >
              <input
                id="dryRun"
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                style={{ width: "auto" }}
              />
              テスト実行にする(実際には入札しない)
            </label>
            <p className="hint">
              確認画面までは本番と同じ手順で進み、最後の確定だけ押しません。
              実行が始まる前(待機中)にだけ切り替えられます。
            </p>
          </div>
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
