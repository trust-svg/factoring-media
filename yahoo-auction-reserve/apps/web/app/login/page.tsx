"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: form.get("email"),
        password: form.get("password"),
      }),
    });
    setBusy(false);
    if (res.ok) {
      router.push("/dashboard");
      router.refresh();
    } else {
      setError((await res.json()).error ?? "ログインに失敗しました");
    }
  }

  return (
    <div className="card">
      <h2>ログイン</h2>
      <form className="form" onSubmit={onSubmit}>
        <div>
          <label htmlFor="email">メールアドレス</label>
          <input id="email" name="email" type="email" required />
        </div>
        <div>
          <label htmlFor="password">パスワード</label>
          <input id="password" name="password" type="password" required />
        </div>
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>ログイン</button>
      </form>
    </div>
  );
}
