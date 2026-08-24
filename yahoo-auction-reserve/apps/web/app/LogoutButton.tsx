"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

// ログアウトは Cookie(yar_session) の破棄をサーバ側で行う必要があるため、
// リンクではなく POST /api/v1/auth/logout を叩く。
// レイアウト(サーバコンポーネント)に置くので、ここだけクライアント境界にする。
export default function LogoutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function onClick() {
    setBusy(true);
    try {
      await fetch("/api/v1/auth/logout", { method: "POST" });
    } finally {
      // 失敗しても画面はログイン前提に戻す(Cookie が残っていれば再度ログイン状態になる)
      setBusy(false);
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <button type="button" className="linklike" onClick={onClick} disabled={busy}>
      {busy ? "ログアウト中…" : "ログアウト"}
    </button>
  );
}
