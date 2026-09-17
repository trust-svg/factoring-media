"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

// 押しても同期はその場で終わらない。worker の30秒走査が拾い、Chromium を
// 起動して1件ずつ商品情報を取りに行くので、体感で1〜2分かかることがある。
//
// ⚠️ 押した直後に router.refresh() しても **必ず古いまま** になる。
//    最終同期時刻が押した時点より進むまで見張ってから再描画すること。
const POLL_INTERVAL_MS = 3000;
const GIVE_UP_MS = 4 * 60 * 1000;

export default function WatchlistSyncButton({
  lastSyncAtMs,
  initialPending,
}: {
  lastSyncAtMs: number | null;
  initialPending: boolean;
}) {
  const router = useRouter();
  const [waiting, setWaiting] = useState(initialPending);
  const [message, setMessage] = useState<string | null>(null);
  const [waitedSec, setWaitedSec] = useState(0);
  // 「終わった」の基準。押した時点の最終同期時刻より新しくなったら完了
  const baseline = useRef<number>(lastSyncAtMs ?? 0);

  useEffect(() => {
    if (!waiting) return;
    const startedAt = Date.now();
    let stopped = false;

    const look = async () => {
      if (stopped) return;
      setWaitedSec(Math.floor((Date.now() - startedAt) / 1000));
      try {
        const res = await fetch("/api/v1/watchlist/sync", { cache: "no-store" });
        if (res.ok) {
          const data: { lastSyncAtMs?: number | null } = await res.json();
          const synced = data.lastSyncAtMs ?? 0;
          if (synced > baseline.current) {
            stopped = true;
            baseline.current = synced;
            setWaiting(false);
            setMessage(null);
            router.refresh();
            return;
          }
        }
      } catch {
        // 1回の通信失敗では諦めない。次の見張りで拾う
      }
      if (Date.now() - startedAt > GIVE_UP_MS) {
        stopped = true;
        setWaiting(false);
        // ⚠️ 「失敗しました」と書かない。要求は残っていて後から反映される
        //    ことがほとんどなので、断定すると嘘になる
        setMessage("まだ同期が終わっていません。少し待ってから再読み込みしてください。");
      }
    };

    const timer = setInterval(look, POLL_INTERVAL_MS);
    void look();
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [waiting, router]);

  const request = async () => {
    setMessage(null);
    try {
      const res = await fetch("/api/v1/watchlist/sync", { method: "POST" });
      const data: { error?: string } = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMessage(data.error ?? "更新を受け付けられませんでした。");
        return;
      }
      setWaitedSec(0);
      setWaiting(true);
    } catch {
      setMessage("更新を要求できませんでした。通信を確認してください。");
    }
  };

  return (
    <p className="notice">
      <button onClick={request} disabled={waiting}>
        {waiting ? `同期中… (${waitedSec}秒)` : "今すぐ更新"}
      </button>
      {waiting
        ? " ヤフオクを開いて読み直しています。1〜2分かかることがあります。"
        : " ふだんは1時間ごとに自動で取り込みます。"}
      {message && ` ${message}`}
    </p>
  );
}
