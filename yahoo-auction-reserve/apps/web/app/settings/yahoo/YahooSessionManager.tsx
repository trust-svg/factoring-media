"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  SESSION_STATUS_LABEL,
  SESSION_VERIFICATION_LABEL,
  sessionVerificationKind,
  type SessionStatusKey,
} from "@yar/shared/labels";

interface SessionRow {
  id: string;
  label: string;
  status: SessionStatusKey;
  lastVerifiedAt: string | null;
  lastVerifyAttemptAt: string | null;
  createdAt: string;
  activeReservations: number;
}

const verifyKind = (s: SessionRow) =>
  sessionVerificationKind(s.lastVerifiedAt, s.lastVerifyAttemptAt);

export default function YahooSessionManager({
  sessions,
}: {
  sessions: SessionRow[];
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError(null);
    setWarnings([]);
    setNotice(null);

    const res = await fetch("/api/v1/yahoo-sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        label: data.get("label"),
        cookiesJson: data.get("cookiesJson"),
      }),
    });
    const body = await res.json();
    setBusy(false);

    if (!res.ok) {
      setError(body.error ?? "連携の登録に失敗しました");
      return;
    }
    form.reset();
    setNotice(
      `「${body.label}」を登録しました(Cookie ${body.cookieCount}件)。` +
        "ログインが生きているかは30秒ほどで自動確認し、下の「最終確認」に出ます",
    );
    setWarnings(body.warnings ?? []);
    router.refresh();
  }

  async function onDelete(session: SessionRow) {
    if (!confirm(`「${session.label}」の連携を解除します。よろしいですか?`)) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await fetch(`/api/v1/yahoo-sessions/${session.id}`, {
      method: "DELETE",
    });
    setBusy(false);
    if (!res.ok) {
      setError((await res.json()).error ?? "連携解除に失敗しました");
      return;
    }
    setNotice("連携を解除しました");
    router.refresh();
  }

  return (
    <>
      <h1>ヤフオク連携</h1>

      <div className="card">
        <h2>連携済みアカウント</h2>
        {sessions.length === 0 && (
          <p className="muted">
            まだ連携がありません。下のフォームから Cookie を登録してください。
          </p>
        )}
        {sessions.map((s) => (
          <div className="row" key={s.id} style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 12 }}>
            <div className="grow">
              <strong>{s.label}</strong>{" "}
              <span className={`badge ${s.status === "ACTIVE" ? "WON" : "FAILED"}`}>
                {SESSION_STATUS_LABEL[s.status]}
              </span>
              <p className="muted">
                登録: {new Date(s.createdAt).toLocaleString("ja-JP")} / 最終確認:{" "}
                {/* 「まだ確認していない」と「確認したが判定できなかった」を
                    同じ表示にしない。後者は待っても解消しない(→ P0 検証が要る)。 */}
                {s.lastVerifiedAt ? (
                  new Date(s.lastVerifiedAt).toLocaleString("ja-JP")
                ) : (
                  <span className={verifyKind(s) === "INCONCLUSIVE" ? "attention" : undefined}>
                    {SESSION_VERIFICATION_LABEL[verifyKind(s)]}
                  </span>
                )}
                {s.activeReservations > 0 &&
                  ` / 実行前の予約 ${s.activeReservations}件`}
              </p>
            </div>
            <button
              className="danger"
              disabled={busy}
              onClick={() => onDelete(s)}
            >
              連携解除
            </button>
          </div>
        ))}
      </div>

      <div className="card">
        <h2>Cookie を登録する</h2>
        <p className="muted">
          Yahoo! JAPAN のパスワードはお預かりしません。ログイン済みのセッション Cookie
          だけを暗号化して保管し、入札実行時にのみ復号します。連携解除で即時削除されます。
        </p>
        <details style={{ marginBottom: 12 }}>
          <summary>Cookie の取り出し方</summary>
          <ol className="muted">
            <li>
              ブラウザでヤフオク(auctions.yahoo.co.jp)に<strong>ログイン</strong>する
            </li>
            <li>
              Cookie エクスポート拡張(Cookie-Editor 等)を開き、
              <code>yahoo.co.jp</code> の Cookie を <strong>JSON 形式でエクスポート</strong>
              してコピーする
            </li>
            <li>下の欄に貼り付けて登録する</li>
          </ol>
          <p className="muted">
            ※ ログインに使う Cookie は httpOnly のため、ブックマークレットや
            <code>document.cookie</code> では取得できません。拡張機能か
            DevTools(Application → Cookies)からのエクスポートが必要です。
            Playwright の <code>storageState</code> 形式もそのまま貼り付けられます。
          </p>
        </details>

        <form className="form" onSubmit={onSubmit}>
          <div>
            <label htmlFor="label">ラベル(表示名)</label>
            <input
              id="label"
              name="label"
              maxLength={50}
              placeholder="メインアカウント"
              required
            />
          </div>
          <div>
            <label htmlFor="cookiesJson">Cookie JSON</label>
            <textarea
              id="cookiesJson"
              name="cookiesJson"
              rows={8}
              placeholder='[{"name":"T","value":"...","domain":".yahoo.co.jp"}, ...]'
              required
            />
          </div>
          {error && <p className="error">{error}</p>}
          {notice && <p className="muted">{notice}</p>}
          {warnings.map((w) => (
            <p className="error" key={w}>
              ⚠ {w}
            </p>
          ))}
          <button disabled={busy}>登録する</button>
        </form>
      </div>
    </>
  );
}
