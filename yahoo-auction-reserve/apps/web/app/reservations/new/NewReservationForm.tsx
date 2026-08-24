"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { totalWithShipping, type Judgement } from "@yar/shared/judgement";

interface AuctionPreview {
  auctionId: string;
  url: string;
  title?: string;
  imageUrl?: string;
  sellerName?: string;
  currentPrice?: number;
  endAt?: string;
  hasAutoExtension?: boolean;
  isClosed?: boolean;
  shippingFee?: number;
  shippingNote?: string;
  sellerRating?: number;
  sellerRatingCount?: number;
  /** 設定したしきい値での足切り判定(preview API が付ける) */
  sellerJudgement?: Judgement;
  /** true ならこのまま登録しても API に断られる */
  sellerBlocks?: boolean;
}

type Step = "url" | "input" | "confirm";

export default function NewReservationForm({
  sessions,
  groups,
  snipeDefaults,
  initialUrl = "",
  telegramLinked,
}: {
  sessions: { id: string; label: string }[];
  groups: { id: string; name: string }[];
  snipeDefaults: { default: number; min: number; max: number };
  /** ウォッチリストから「予約する」で来たときの初期URL */
  initialUrl?: string;
  /** Telegram の chat ID が登録済みか。未登録だと承認制は成立しない */
  telegramLinked: boolean;
}) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("url");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [url, setUrl] = useState(initialUrl);
  const [preview, setPreview] = useState<AuctionPreview | null>(null);
  const [maxBidAmount, setMaxBidAmount] = useState("");
  const [snipeSeconds, setSnipeSeconds] = useState(String(snipeDefaults.default));
  const [yahooSessionId, setYahooSessionId] = useState(sessions[0]?.id ?? "");
  const [autoRaiseMode, setAutoRaiseMode] = useState<"OFF" | "AUTO" | "APPROVAL">("OFF");
  const [absoluteMaxAmount, setAbsoluteMaxAmount] = useState("");
  const [autoRaiseStep, setAutoRaiseStep] = useState("500");
  const [autoRaiseMaxCount, setAutoRaiseMaxCount] = useState("3");
  // "" = グループなし / "__new" = 新規作成 / それ以外は既存グループのID
  const [groupChoice, setGroupChoice] = useState("");
  const [newGroupName, setNewGroupName] = useState("");

  const endAt = preview?.endAt ? new Date(preview.endAt) : null;
  const executeAt =
    endAt && Number.isFinite(endAt.getTime())
      ? new Date(endAt.getTime() - Number(snipeSeconds) * 1000)
      : null;

  async function onPreview(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/v1/auctions/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const body = await res.json();
    setBusy(false);
    if (!res.ok) {
      setError(body.error ?? "商品情報の取得に失敗しました");
      return;
    }
    if (body.isClosed) {
      setError("このオークションは既に終了しています");
      return;
    }
    setPreview(body);
    // 上限額の初期値は空のまま(誤って現在価格で確定させないため)
    setStep("input");
  }

  function onGoConfirm(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const amount = Number(maxBidAmount);
    if (!Number.isInteger(amount) || amount <= 0) {
      setError("上限入札額は正の整数で入力してください");
      return;
    }
    if (preview?.currentPrice !== undefined && amount <= preview.currentPrice) {
      setError(
        `上限額は現在価格(${preview.currentPrice.toLocaleString()}円)より高くしてください`,
      );
      return;
    }
    const secs = Number(snipeSeconds);
    if (
      !Number.isInteger(secs) ||
      secs < snipeDefaults.min ||
      secs > snipeDefaults.max
    ) {
      setError(
        `実行タイミングは${snipeDefaults.min}〜${snipeDefaults.max}秒前で指定してください`,
      );
      return;
    }
    if (autoRaiseMode !== "OFF") {
      const abs = Number(absoluteMaxAmount);
      if (!Number.isInteger(abs) || abs <= amount) {
        setError(`絶対上限は上限額(${amount.toLocaleString()}円)より高い整数で入力してください`);
        return;
      }
      if (!Number.isInteger(Number(autoRaiseStep)) || Number(autoRaiseStep) < 10) {
        setError("1回あたりの増額幅は10円以上で入力してください");
        return;
      }
      const cnt = Number(autoRaiseMaxCount);
      if (!Number.isInteger(cnt) || cnt < 1 || cnt > 20) {
        setError("増額の回数上限は1〜20回で入力してください");
        return;
      }
    }
    if (groupChoice === "__new" && newGroupName.trim().length === 0) {
      setError("新しいグループ名を入力してください");
      return;
    }
    setStep("confirm");
  }

  async function onSubmit() {
    setBusy(true);
    setError(null);

    // 新規グループは予約より先に作る。ここで失敗したら予約自体を止める
    // (グループ無しで登録すると「取りやめてくれるはず」の前提が黙って崩れる)。
    let groupId: string | null = groupChoice && groupChoice !== "__new" ? groupChoice : null;
    if (groupChoice === "__new") {
      const gres = await fetch("/api/v1/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newGroupName }),
      });
      const gbody = await gres.json();
      if (!gres.ok) {
        setBusy(false);
        setError(gbody.error ?? "グループの作成に失敗しました");
        setStep("input");
        return;
      }
      groupId = gbody.id;
    }

    const res = await fetch("/api/v1/reservations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: preview?.url ?? url,
        maxBidAmount: Number(maxBidAmount),
        snipeSecondsBefore: Number(snipeSeconds),
        yahooSessionId,
        autoRaiseMode,
        absoluteMaxAmount: autoRaiseMode === "OFF" ? null : Number(absoluteMaxAmount),
        autoRaiseStep: autoRaiseMode === "OFF" ? null : Number(autoRaiseStep),
        autoRaiseMaxCount: autoRaiseMode === "OFF" ? null : Number(autoRaiseMaxCount),
        groupId,
      }),
    });
    const body = await res.json();
    setBusy(false);
    if (!res.ok) {
      setError(body.error ?? "予約の登録に失敗しました");
      setStep("input");
      return;
    }
    router.push(`/reservations/${body.id}`);
    router.refresh();
  }

  return (
    <>
      <h1>新規予約</h1>

      {/* ---- STEP 1: URL ---- */}
      <div className="card">
        <h2>1. 商品URL</h2>
        <form className="form" onSubmit={onPreview}>
          <div>
            <label htmlFor="url">ヤフオクの商品URL</label>
            <input
              id="url"
              name="url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setPreview(null);
                setStep("url");
              }}
              placeholder="https://page.auctions.yahoo.co.jp/jp/auction/x1234567890"
              required
            />
          </div>
          {step === "url" && error && <p className="error">{error}</p>}
          <button disabled={busy || url.length === 0}>
            {busy ? "取得中…" : "商品情報を取得"}
          </button>
        </form>
      </div>

      {/* ---- STEP 2: 条件入力 ---- */}
      {preview && (
        <div className="card">
          <h2>2. 入札条件</h2>
          <div className="row">
            {preview.imageUrl && (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img className="thumb" src={preview.imageUrl} alt="" />
            )}
            <div className="grow">
              <strong>{preview.title ?? preview.auctionId}</strong>
              <p className="muted">
                現在価格{" "}
                {preview.currentPrice !== undefined
                  ? `${preview.currentPrice.toLocaleString()}円`
                  : "取得できませんでした"}{" "}
                / 終了{" "}
                {endAt ? endAt.toLocaleString("ja-JP") : "取得できませんでした"}
              </p>
              {preview.hasAutoExtension ? (
                <p className="muted">
                  [自動延長あり] 終了5分前以降に高値更新があると終了が延びます。
                  延長を検知した場合、上限額の範囲内で自動的に再入札します。
                </p>
              ) : (
                <p className="muted">[自動延長なし]</p>
              )}
              <FactsLine preview={preview} />
            </div>
          </div>

          <form className="form" onSubmit={onGoConfirm} style={{ marginTop: 12 }}>
            <div>
              <label htmlFor="maxBidAmount">上限入札額(円)</label>
              <input
                id="maxBidAmount"
                type="number"
                inputMode="numeric"
                value={maxBidAmount}
                onChange={(e) => setMaxBidAmount(e.target.value)}
                required
              />
              <p className="muted">
                ヤフオクは自動入札制のため、上限額を入れても支払額は競合相手の入札額
                +入札単位までに収まります。
              </p>
            </div>
            <div>
              <label htmlFor="snipeSeconds">実行タイミング(終了何秒前)</label>
              <input
                id="snipeSeconds"
                type="number"
                min={snipeDefaults.min}
                max={snipeDefaults.max}
                value={snipeSeconds}
                onChange={(e) => setSnipeSeconds(e.target.value)}
                required
              />
              <p className="muted">
                {snipeDefaults.min}〜{snipeDefaults.max}秒前で指定できます。
                短くするほど他の入札者に気づかれにくい一方、サイト混雑時に
                入札が間に合わないリスクが上がります(既定 {snipeDefaults.default}秒)。
              </p>
            </div>
            <div>
              <label htmlFor="autoRaiseMode">高値更新されたときの自動増額</label>
              <select
                id="autoRaiseMode"
                value={autoRaiseMode}
                onChange={(e) =>
                  setAutoRaiseMode(e.target.value as "OFF" | "AUTO" | "APPROVAL")
                }
              >
                <option value="OFF">増額しない(上限額で打ち止め)</option>
                <option value="AUTO">自動で増額する</option>
                <option value="APPROVAL" disabled={!telegramLinked}>
                  Telegram で承認してから増額する
                  {telegramLinked ? "" : "(要 Telegram 連携)"}
                </option>
              </select>
              <p className="muted">
                上限額を超えられたときに、絶対上限までの範囲で入札しなおします。
                承認制は終了間際ではなく<strong>価格更新を見た時点</strong>で聞くので、
                終了直前に上回られた場合は増額されません。
              </p>
            </div>

            {autoRaiseMode !== "OFF" && (
              <>
                <div>
                  <label htmlFor="absoluteMaxAmount">
                    絶対上限(円) — ここを超える入札は絶対にしません
                  </label>
                  <input
                    id="absoluteMaxAmount"
                    type="number"
                    inputMode="numeric"
                    value={absoluteMaxAmount}
                    onChange={(e) => setAbsoluteMaxAmount(e.target.value)}
                    required
                  />
                </div>
                <div className="field-row">
                  <div>
                    <label htmlFor="autoRaiseStep">1回の増額幅(円)</label>
                    <input
                      id="autoRaiseStep"
                      type="number"
                      inputMode="numeric"
                      value={autoRaiseStep}
                      onChange={(e) => setAutoRaiseStep(e.target.value)}
                      required
                    />
                  </div>
                  <div>
                    <label htmlFor="autoRaiseMaxCount">増額の回数上限</label>
                    <input
                      id="autoRaiseMaxCount"
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={20}
                      value={autoRaiseMaxCount}
                      onChange={(e) => setAutoRaiseMaxCount(e.target.value)}
                      required
                    />
                  </div>
                </div>
                <p className="muted">
                  増額しても現在価格を上回れない額になる場合は、回数を消費せずに見送ります。
                </p>
              </>
            )}

            <div>
              <label htmlFor="groupChoice">グループ(任意)</label>
              <select
                id="groupChoice"
                value={groupChoice}
                onChange={(e) => setGroupChoice(e.target.value)}
              >
                <option value="">グループに入れない</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
                <option value="__new">+ 新しいグループを作る</option>
              </select>
              {groupChoice === "__new" && (
                <input
                  aria-label="新しいグループ名"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="例: ニコン F3 どれか1台"
                  style={{ marginTop: 8 }}
                />
              )}
              <p className="muted">
                同じグループのどれか1つを落札したら、残りの予約は自動で取りやめます
                (「同じ物を2台落札してしまう」を防ぐための束です)。
              </p>
            </div>

            <div>
              <label htmlFor="yahooSessionId">実行に使うヤフオク連携</label>
              <select
                id="yahooSessionId"
                value={yahooSessionId}
                onChange={(e) => setYahooSessionId(e.target.value)}
              >
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            {step === "input" && error && <p className="error">{error}</p>}
            <button disabled={busy}>確認画面へ</button>
          </form>
        </div>
      )}

      {/* ---- STEP 3: 確認(誤発注防止・設計 §10 / S-8) ---- */}
      {step === "confirm" && preview && (
        <div className="card">
          <h2>3. 内容の確認</h2>
          <p>この内容で入札を予約します。よろしければ「予約を確定する」を押してください。</p>
          <table>
            <tbody>
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>商品</th>
                <td>{preview.title ?? preview.auctionId}</td>
              </tr>
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>上限入札額</th>
                <td>
                  <strong>{Number(maxBidAmount).toLocaleString()}円</strong>
                </td>
              </tr>
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>自動増額</th>
                <td>
                  {autoRaiseMode === "OFF"
                    ? "しない"
                    : `${autoRaiseMode === "AUTO" ? "自動" : "Telegram 承認制"} / 絶対上限 ${Number(absoluteMaxAmount).toLocaleString()}円 / ${autoRaiseStep}円ずつ 最大${autoRaiseMaxCount}回`}
                </td>
              </tr>
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>入札実行時刻</th>
                <td>
                  {executeAt ? executeAt.toLocaleString("ja-JP") : "—"}(終了
                  {snipeSeconds}秒前)
                </td>
              </tr>
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>終了予定</th>
                <td>{endAt ? endAt.toLocaleString("ja-JP") : "—"}</td>
              </tr>
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>グループ</th>
                <td>
                  {groupChoice === "__new"
                    ? `${newGroupName}(新規作成)`
                    : (groups.find((g) => g.id === groupChoice)?.name ?? "なし")}
                </td>
              </tr>
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>使用する連携</th>
                <td>{sessions.find((s) => s.id === yahooSessionId)?.label}</td>
              </tr>
            </tbody>
          </table>
          {error && <p className="error">{error}</p>}
          <div className="row" style={{ marginTop: 12 }}>
            <button className="secondary" disabled={busy} onClick={() => setStep("input")}>
              戻って修正
            </button>
            <button disabled={busy} onClick={onSubmit}>
              {busy ? "登録中…" : "予約を確定する"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

/**
 * 判断材料(送料込み総額・出品者評価)の1行表示。
 *
 * ⚠️ 取れなかった項目は「—」ではなく「取得できませんでした」と書く。
 * 空欄にすると「送料無料」「評価に問題なし」と読まれる。
 */
function FactsLine({ preview }: { preview: AuctionPreview }) {
  const { total } = totalWithShipping(
    preview.currentPrice ?? null,
    preview.shippingFee ?? null,
  );
  const judgement = preview.sellerJudgement;

  return (
    <>
      <p className="muted">
        送料{" "}
        {preview.shippingFee === 0
          ? "無料"
          : preview.shippingFee !== undefined
            ? `${preview.shippingFee.toLocaleString()}円`
            : (preview.shippingNote ?? "取得できませんでした")}
        {total != null && ` / 現時点の総額 ${total.toLocaleString()}円`}
        {" / 出品者評価 "}
        {preview.sellerRating !== undefined
          ? `${preview.sellerRating}%${
              preview.sellerRatingCount !== undefined
                ? `(${preview.sellerRatingCount.toLocaleString()}件)`
                : ""
            }`
          : "取得できませんでした"}
      </p>
      {judgement && judgement.level !== "ok" && judgement.reasons.length > 0 && (
        <p className={judgement.level === "warn" ? "error" : "muted"}>
          {judgement.level === "warn" ? "⚠ " : ""}
          {judgement.reasons.join(" / ")}
          {preview.sellerBlocks && "(足切り設定により、このままでは予約できません)"}
        </p>
      )}
    </>
  );
}
