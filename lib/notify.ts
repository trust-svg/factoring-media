const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID;
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;

export async function notifyEstimate(data: {
  businessType: string;
  invoiceAmount: number;
  urgency: string;
  email: string;
  phone?: string | null;
  memo?: string | null;
}) {
  const message = [
    "📩 ファクセル新規問い合わせ",
    "",
    `業種: ${data.businessType}`,
    `売掛金額: ${data.invoiceAmount.toLocaleString()}円`,
    `緊急度: ${data.urgency}`,
    `メール: ${data.email}`,
    data.phone ? `電話: ${data.phone}` : null,
    data.memo ? `メモ: ${data.memo}` : null,
    "",
    `時刻: ${new Date().toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })}`,
  ]
    .filter(Boolean)
    .join("\n");

  if (TELEGRAM_BOT_TOKEN) {
    try {
      await fetch(
        `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chat_id: TELEGRAM_CHAT_ID,
            text: message,
            parse_mode: "HTML",
          }),
        }
      );
    } catch (e) {
      console.error("Telegram notification failed:", e);
    }
  } else {
    console.warn("TELEGRAM_BOT_TOKEN not set, skipping notification");
  }
}
