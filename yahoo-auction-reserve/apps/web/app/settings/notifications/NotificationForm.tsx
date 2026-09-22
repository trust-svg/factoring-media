"use client";

import { useState } from "react";

const PRESETS = [
  { minutes: 1440, label: "1日前" },
  { minutes: 360, label: "6時間前" },
  { minutes: 60, label: "1時間前" },
  { minutes: 30, label: "30分前" },
  { minutes: 10, label: "10分前" },
  { minutes: 5, label: "5分前" },
];

export interface NotificationFormValue {
  telegramChatId: string;
  remindMinutesBefore: number[];
  notifyResult: boolean;
  notifyError: boolean;
  dailySummaryAt: string;
}

export default function NotificationForm({
  initial,
  telegramConfigured,
}: {
  initial: NotificationFormValue;
  telegramConfigured: boolean;
}) {
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const set = <K extends keyof NotificationFormValue>(
    key: K,
    v: NotificationFormValue[K],
  ) => {
    setValue((prev) => ({ ...prev, [key]: v }));
    setSaved(false);
  };

  const toggleMinutes = (m: number) => {
    const has = value.remindMinutesBefore.includes(m);
    set(
      "remindMinutesBefore",
      has
        ? value.remindMinutesBefore.filter((x) => x !== m)
        : [...value.remindMinutesBefore, m].sort((a, b) => b - a),
    );
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/notification-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(value),
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
      {!telegramConfigured && (
        <p className="error">
          サーバに <code>TELEGRAM_BOT_TOKEN</code> が設定されていません。
          この状態では Telegram には何も届きません(承認制の自動増額も成立しません)。
        </p>
      )}

      <div>
        <label htmlFor="chatId">Telegram の chat ID</label>
        <input
          id="chatId"
          inputMode="numeric"
          value={value.telegramChatId}
          placeholder="323107833"
          onChange={(e) => set("telegramChatId", e.target.value)}
        />
        <p className="hint">
          Bot に何か1通送ってから <code>getUpdates</code> を開き、
          <code>message.chat.id</code> の値を入れる。空にすると Telegram 送信を止める。
        </p>
      </div>

      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <label>終了前のリマインド(最大5件)</label>
        <div className="row">
          {PRESETS.map((p) => (
            <label className="check" key={p.minutes}>
              <input
                type="checkbox"
                checked={value.remindMinutesBefore.includes(p.minutes)}
                onChange={() => toggleMinutes(p.minutes)}
              />
              {p.label}
            </label>
          ))}
        </div>
        <p className="hint">
          予約ごとではなく全予約に適用される。同じ予約・同じ分指定には一度しか送らない。
        </p>
      </fieldset>

      <label className="check">
        <input
          type="checkbox"
          checked={value.notifyResult}
          onChange={(e) => set("notifyResult", e.target.checked)}
        />
        入札結果(落札 / 落札ならず)を通知する
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={value.notifyError}
          onChange={(e) => set("notifyError", e.target.checked)}
        />
        異常系(失敗・ログイン切れ・上限超過でのスキップ)を通知する
      </label>
      <p className="hint">
        承認依頼は上の設定に関わらず必ず送る。届かない = 増額しない、という実害に
        直結するため切れないようにしてある。
      </p>

      <div>
        <label htmlFor="summary">毎日の稼働サマリ(JST)</label>
        <input
          id="summary"
          value={value.dailySummaryAt}
          placeholder="08:00"
          onChange={(e) => set("dailySummaryAt", e.target.value)}
        />
        <p className="hint">
          予約件数・直近24時間の結果・通知の失敗件数をまとめて送る。
          <strong>これが届かないこと自体が worker 停止の合図</strong>になるので、
          動かしているなら設定しておく。空にすると送らない。
        </p>
      </div>

      {error && <p className="error">{error}</p>}
      {saved && <p className="muted">保存しました。</p>}
      <div className="row">
        <button type="submit" disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </button>
      </div>
    </form>
  );
}
