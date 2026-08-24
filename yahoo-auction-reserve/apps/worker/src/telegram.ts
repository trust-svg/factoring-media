// Telegram Bot API の薄いクライアント(設計 §9 の通知経路)。
//
// ⚠️ URL に Bot トークンが埋まる API なので、**例外・ログに URL をそのまま出さない**。
// fetch の失敗メッセージには URL が入るため、外へ出す文字列は必ず redact() を通す。
//
// ⚠️ getUpdates は 1 Bot につき 1 消費者しか許されない(webhook とも排他)。
// worker を 2 つ動かすと片方が 409 Conflict を受け続け、**承認ボタンだけが
// 無言で効かなくなる**。409 は握りつぶさず、そのまま警告として出す。

const API_BASE = "https://api.telegram.org";

export function telegramToken(): string | null {
  const t = process.env.TELEGRAM_BOT_TOKEN;
  return t && t.trim() ? t.trim() : null;
}

export function telegramEnabled(): boolean {
  return telegramToken() !== null;
}

/** トークンを含みうる文字列から、トークンを消す */
function redact(input: unknown): string {
  const s = input instanceof Error ? input.message : String(input);
  const token = telegramToken();
  if (!token) return s;
  return s.split(token).join("<TELEGRAM_BOT_TOKEN>");
}

export class TelegramError extends Error {
  constructor(
    message: string,
    readonly statusCode: number | null,
  ) {
    super(redact(message));
    this.name = "TelegramError";
  }
}

interface TelegramResponse<T> {
  ok: boolean;
  result?: T;
  description?: string;
  error_code?: number;
}

async function callApi<T>(
  method: string,
  body: Record<string, unknown>,
  timeoutMs = 15_000,
): Promise<T> {
  const token = telegramToken();
  if (!token) throw new TelegramError("TELEGRAM_BOT_TOKEN が未設定です", null);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/bot${token}/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    throw new TelegramError(`${method} の送信に失敗: ${redact(err)}`, null);
  } finally {
    clearTimeout(timer);
  }

  const json = (await res.json().catch(() => null)) as TelegramResponse<T> | null;
  if (!json?.ok) {
    const code = json?.error_code ?? res.status;
    throw new TelegramError(
      `${method} が拒否されました (${code}): ${redact(json?.description ?? "詳細なし")}`,
      code,
    );
  }
  return json.result as T;
}

/** Telegram の HTML パースモードで壊れない形にする */
export function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export interface InlineButton {
  text: string;
  callbackData: string;
}

export interface SentMessage {
  messageId: number;
  chatId: string;
}

export async function sendTelegram(
  chatId: string,
  html: string,
  buttons?: InlineButton[],
): Promise<SentMessage> {
  const result = await callApi<{ message_id: number }>("sendMessage", {
    chat_id: chatId,
    text: html,
    parse_mode: "HTML",
    // プレビュー展開でヤフオクへ大量アクセスしない・通知が縦に伸びない
    link_preview_options: { is_disabled: true },
    ...(buttons?.length
      ? {
          reply_markup: {
            inline_keyboard: [
              buttons.map((b) => ({ text: b.text, callback_data: b.callbackData })),
            ],
          },
        }
      : {}),
  });
  return { messageId: result.message_id, chatId };
}

/** 承認済み/期限切れのメッセージからボタンを外し、本文を結果に差し替える */
export async function editTelegramMessage(
  chatId: string,
  messageId: number,
  html: string,
): Promise<void> {
  await callApi("editMessageText", {
    chat_id: chatId,
    message_id: messageId,
    text: html,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
    reply_markup: { inline_keyboard: [] },
  });
}

/** ボタンを押した側のローディングを止める。返さないと数秒回り続ける */
export async function answerCallbackQuery(
  callbackQueryId: string,
  text?: string,
): Promise<void> {
  await callApi("answerCallbackQuery", {
    callback_query_id: callbackQueryId,
    ...(text ? { text } : {}),
  });
}

export interface CallbackUpdate {
  updateId: number;
  callbackQueryId: string;
  data: string;
  chatId: string;
  messageId: number;
  fromId: string;
}

interface RawUpdate {
  update_id: number;
  callback_query?: {
    id: string;
    data?: string;
    from: { id: number };
    message?: { message_id: number; chat: { id: number } };
  };
}

/**
 * long polling で callback_query(インライン button の押下)だけを拾う。
 * 公開 URL が要らないので webhook を立てずに済む。
 *
 * offset は「次に受け取りたい update_id」。処理済みを確定させるために
 * 呼び出し側が返り値の最大 updateId + 1 を次回に渡すこと。
 */
export async function pollCallbacks(
  offset: number,
  timeoutSeconds = 25,
): Promise<CallbackUpdate[]> {
  const updates = await callApi<RawUpdate[]>(
    "getUpdates",
    {
      offset,
      timeout: timeoutSeconds,
      allowed_updates: ["callback_query"],
    },
    (timeoutSeconds + 10) * 1000,
  );

  const out: CallbackUpdate[] = [];
  for (const u of updates) {
    const cq = u.callback_query;
    if (!cq?.data || !cq.message) continue;
    out.push({
      updateId: u.update_id,
      callbackQueryId: cq.id,
      data: cq.data,
      chatId: String(cq.message.chat.id),
      messageId: cq.message.message_id,
      fromId: String(cq.from.id),
    });
  }
  return out;
}

/** 最大の update_id。処理済み位置(offset)を進めるのに使う */
export function nextOffset(updates: CallbackUpdate[], current: number): number {
  return updates.reduce((max, u) => Math.max(max, u.updateId + 1), current);
}
