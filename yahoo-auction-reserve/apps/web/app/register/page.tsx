"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (!form.get("agree")) {
      setError("利用上の注意への同意が必要です");
      return;
    }
    setBusy(true);
    setError(null);
    const res = await fetch("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: form.get("email"),
        password: form.get("password"),
      }),
    });
    setBusy(false);
    if (res.ok) {
      router.push("/settings/yahoo");
      router.refresh();
    } else {
      setError((await res.json()).error ?? "登録に失敗しました");
    }
  }

  return (
    <div className="card">
      <h2>新規登録</h2>
      <form className="form" onSubmit={onSubmit}>
        <div>
          <label htmlFor="email">メールアドレス</label>
          <input id="email" name="email" type="email" required />
        </div>
        <div>
          <label htmlFor="password">パスワード(8文字以上)</label>
          <input id="password" name="password" type="password" minLength={8} required />
        </div>
        <label>
          <input type="checkbox" name="agree" />{" "}
          外部ツールによる自動入札にはアカウント制限等のリスクがあること、入札失敗による
          機会損失は補償されないことに同意します
        </label>
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>同意して登録</button>
      </form>
    </div>
  );
}
