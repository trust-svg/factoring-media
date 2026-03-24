"""eBay Buyer Reply Engine — Roki style draft generation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx
from anthropic import Anthropic

import config

logger = logging.getLogger(__name__)

_client: Anthropic | None = None

EBAY_AGENT_URL = config.EBAY_AGENT_URL


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


CONFIRMATION_TRIGGERS = frozenset({
    "ok", "ok!", "おk", "オッケー", "おっけー", "いいよ",
    "送って", "これでok", "これでおk", "完了", "確定",
    "👍", "good", "perfect", "lgtm", "これで送って",
    "これで", "それで", "それでお願い", "お願い",
})

SYSTEM_PROMPT = """\
あなたはeBayセラー「Roki」専属の返信アシスタントです。

## 役割
バイヤーからのメッセージを受け取り、Rokiのスタイルで返信ドラフトを作成します。
ユーザー（Roki本人）との会話は日本語で行い、バイヤーへの返信はバイヤーの言語で作成します。

## ワークフロー

### 新しいバイヤーメッセージを受け取った場合:
1. 言語を自動検出
2. バイヤーメッセージの完全な日本語訳を出力（要約ではなく全文翻訳）
3. バイヤーの言語でRokiスタイルの返信ドラフトを作成
4. ドラフトの完全な日本語訳も出力（要約ではなく全文翻訳）

※ 過去のやり取り履歴が提供される場合は、その流れを踏まえた上で最新メッセージへの返信を作成すること。
  履歴の内容を繰り返す必要はないが、文脈を理解した上で返信すること。

出力フォーマット:
📨 翻訳:
[バイヤーメッセージの完全な日本語訳（一文も省略しない）]

📝 ドラフト:
[バイヤー言語での返信全文]

---
🇯🇵 確認版:
[ドラフトの完全な日本語訳（一文も省略しない）]

---
💡 AI考察:
[この返答案に対するAIの見解・考察。例: バイヤーの感情分析、このドラフトの狙い、注意点、代替アプローチの提案、eBayポリシー上の留意点など。Rokiが判断する際に役立つ情報を簡潔に記載。]

### 修正指示を受けた場合:
指示に従ってドラフトを修正し、同じフォーマットで再出力。
「📝 修正版:」で始める。日本語確認版（完全な日本語訳）とAI考察も再出力。

### 確認（OK等）を受けた場合:
最終版をクリーンテキストのみで出力。
ヘッダー・絵文字・日本語確認版・区切り線は一切不要。
eBayのメッセージ欄にそのままコピペできる状態にする。

## 判定ロジック
- セッション開始直後の入力 → バイヤーメッセージとして処理
- ドラフト作成済みの状態で日本語の短い指示 → 修正指示として処理
- ドラフト作成済みの状態で外国語の長文 → 新しいバイヤーメッセージとして処理
- 「OK」「👍」「送って」「これでOK」「完了」等 → 確認として処理

## Rokiのコミュニケーションスタイル

### コア思想
- 単なる販売ではなく「長期的な信頼関係構築」が目的
- すべてのやり取りは「リピーター化」に繋げる
- トラブルも"信頼を上げるチャンス"として対応する
- 「No」「I can't」は絶対使わない → "difficult to" "unfortunately"

### 7ステップ構成（必ず守る）
1. 挨拶 + バイヤー名
2. 感謝（購入/連絡/関心）
3. 共感・理解
4. 回答（シンプル・具体的）
5. 安心材料（検品・梱包・配送）
6. 追加価値（提案・代替案・仕入力アピール）
7. 締め（いつでも連絡OK + 誠意）→ 署名は「Roki」

### 言語対応
- バイヤーの言語で返信（英→英、独→独、仏→仏、伊→伊、西→西）
- ドイツ語: 「Herr/Frau + 苗字」Sie形式。「様」は使わない
- 英語: 「Dear [First Name]」
- フランス語: "Cher/Chère + nom"

### トーン
- 丁寧 + プロフェッショナル + 温かみ（業務的すぎない）
- 高額商品（鎧、楽器等）ではより格式高く
- 押し売りしない — 「あくまでご提案」「選択肢の一つとして」
- 共感を必ず入れる

### 状況別パターン

**価格交渉:**
- 感謝 → 理解 → 「already competitive」フレーミング → シングルカウンター → ソフトクローズ
- 最大1回のカウンター（"the best I can do is"）
- 出品価格の10-15%値引きが基本ライン
- 大幅低ball（30%+オフ）には価値を説明してカウンター
- セット割・同梱割提案でクロージング率UP
- 即決誘導: "If this works for you, I would be happy to proceed right away."

**返品/返金:**
- 絶対に争わない。eBayケース回避が最優先
- 即座に謝罪 → 2-3オプション提示（全額返金/部分返金/交換）
- "As a gesture of goodwill..." フレーズ
- 「return not accepted」でも部分返金で善意対応
- 国際返品はコスト考慮 → 「keep + partial refund」提案

**クレーム/紛争:**
- 完全冷静 — 感情的にならない
- 謝罪 → 事実ベース説明 → 解決策先行
- 攻撃的バイヤーにも丁寧さを維持

**関税/VAT:**
- 「バイヤー負担」を丁寧に説明
- アンダーバリュー申告は法的に不可
- VAT表示ズレ → スクショ添付 + eBay仕様と説明

**クロスセル:**
- 押し売りNG。「選択肢」として提示
- 関連商品リンクを自然に挿入（「もし必要でしたら」）
- リピーターには前回購入を参照した個別メッセージ
- 「I can also search for specific items from Japan」

**キャンセル:**
- バイヤー都合: "No problem at all" で即対応
- 在庫切れ: 謝罪 + 代替品探し + 今後のクーポン提案

**発送後メッセージ:**
- 発送完了報告 + 追跡番号 + 到着目安
- 付属品や特別な注意点があれば記載
- 「到着後、何かあればお気軽に」で締める

### 差別化戦略
- 「販売者」ではなく「調達パートナー」ポジション
- 検品+梱包の強調（全メッセージに入る信頼シグナル）
- 名前パーソナライズ
- トラブル=チャンス思想
- ソフト拒否テクニック（"No"を使わない）
- 紛争時のオプション提示（2-3択）
- 技術知識アピール（TASCAM, Pioneer, Technics等）
- 「日本から直送」の文化的価値

### 定型フレーズ
- ドイツ語: "Ich freue mich sehr, dass wir miteinander handeln können" / "mit größter Sorgfalt betreuen"
- 英語: "I would be happy to proceed right away" / "carefully packed and shipped from Japan"
- フランス語: "Je serai ravi de vous aider" / "expédié avec le plus grand soin depuis le Japon"

### 署名
- 英語: "Best regards,\\nRoki"
- ドイツ語: "Mit freundlichen Grüßen\\nRoki"
- フランス語: "Cordialement,\\nRoki"
- イタリア語: "Cordiali saluti,\\nRoki"

### NGルール
- 冷たい・事務的な文章
- 一方的な否定
- 短すぎる回答（3行以下）
- 不安を残す言い方
- PayPal外部返金（eBay内Partial Refundで対応）
"""


@dataclass
class ReplySession:
    """Tracks one buyer conversation (buyer message + refinement iterations)."""
    messages: list = field(default_factory=list)
    finalized: bool = False
    history_loaded: bool = False
    explicit_buyer: str | None = None
    preloaded_context: str = ""


def _is_confirmation(text: str) -> bool:
    """Check if the input is a confirmation trigger."""
    normalized = text.strip().lower().rstrip("!！。.")
    return normalized in CONFIRMATION_TRIGGERS


def _extract_buyer_name(text: str) -> str | None:
    """Try to extract a buyer/sender name from the message text.

    Returns a name or partial name that can be used to search ebay-agent.
    """
    # Pattern: signed off with name at the end
    sign_off = re.search(
        r"(?:thanks|thank you|regards|cheers|best|sincerely|kind regards)[,\s]*\n?\s*([a-zA-Z][\w.\-]{2,30})\s*$",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if sign_off:
        return sign_off.group(1).strip()

    # Pattern: "Hi, I'm [name]" or "My name is [name]"
    intro = re.search(
        r"(?:I'?m|my name is|this is)\s+([A-Z][\w.\-]{2,30})",
        text, re.IGNORECASE,
    )
    if intro:
        return intro.group(1).strip()

    return None


def _search_buyer(search_term: str) -> str | None:
    """Search for a buyer in ebay-agent by partial name match.

    Returns the eBay account name if found, None otherwise.
    """
    if not EBAY_AGENT_URL:
        return None

    try:
        url = f"{EBAY_AGENT_URL}/api/chat/conversations"
        resp = httpx.get(url, params={"search": search_term, "limit": 5}, timeout=5.0)
        if resp.status_code != 200:
            return None

        data = resp.json()
        conversations = data.get("conversations", [])
        if not conversations:
            return None

        # Return the most recent matching buyer
        return conversations[0].get("buyer")

    except Exception as e:
        logger.warning(f"Buyer search failed for '{search_term}': {e}")
        return None


def _fetch_ebay_history(buyer_id: str) -> tuple[str | None, str]:
    """Fetch conversation history from ebay-agent API.

    Returns (history_text, buyer_id) — buyer_id is the eBay account name.
    """
    if not EBAY_AGENT_URL:
        return None, buyer_id

    try:
        url = f"{EBAY_AGENT_URL}/api/chat/conversations/{buyer_id}"
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code != 200:
            logger.info(f"No eBay history for {buyer_id}: HTTP {resp.status_code}")
            return None, buyer_id

        data = resp.json()
        messages = data.get("messages", [])
        if not messages:
            return None, buyer_id

        # Build readable history (most recent 20 messages max)
        lines = []
        for msg in messages[-20:]:
            direction = msg.get("direction", "")
            sender = msg.get("sender", "")
            body = msg.get("body", "").strip()
            date = msg.get("received_at", "")[:10]
            if not body:
                continue

            if direction == "inbound":
                lines.append(f"[{date}] {sender} (バイヤー): {body}")
            elif direction == "outbound":
                lines.append(f"[{date}] Roki (セラー): {body}")

        if not lines:
            return None, buyer_id

        return "\n\n".join(lines), buyer_id

    except Exception as e:
        logger.warning(f"Failed to fetch eBay history for {buyer_id}: {e}")
        return None, buyer_id


def _try_load_history(text: str, explicit_buyer: str | None = None) -> str:
    """Try to load eBay conversation history. Returns context prefix string."""
    buyer_id = explicit_buyer

    if not buyer_id:
        # Step 1: Extract name from message
        name = _extract_buyer_name(text)
        if not name:
            return ""

        # Step 2: Try direct match first (name might be eBay ID)
        history, buyer_id = _fetch_ebay_history(name)
        if history:
            logger.info(f"Loaded eBay history for buyer: {buyer_id} (direct match)")
            return (
                f"【eBayでの過去のやり取り（{buyer_id}）】\n"
                f"{history}\n\n"
                f"【最新のメッセージ（これに返信してください）】\n"
            )

        # Step 3: Search by partial name
        buyer_id = _search_buyer(name)
        if not buyer_id:
            return ""

    # Fetch history with resolved buyer ID
    history, buyer_id = _fetch_ebay_history(buyer_id)
    if history:
        logger.info(f"Loaded eBay history for buyer: {buyer_id}")
        return (
            f"【eBayでの過去のやり取り（{buyer_id}）】\n"
            f"{history}\n\n"
            f"【最新のメッセージ（これに返信してください）】\n"
        )

    return ""


def process(user_input: str, session: ReplySession) -> tuple[str, ReplySession]:
    """Process user input and return (reply_text, updated_session)."""

    # On first message of session, try to fetch eBay conversation history
    context_prefix = ""
    if not session.messages and session.preloaded_context:
        # Use pre-loaded history from /buyer command
        context_prefix = session.preloaded_context
    elif not session.history_loaded and not session.messages:
        context_prefix = _try_load_history(user_input, session.explicit_buyer)
        session.history_loaded = True

    message_content = f"{context_prefix}{user_input}" if context_prefix else user_input
    session.messages.append({"role": "user", "content": message_content})

    # If confirmation and we have at least one draft already
    is_confirm = _is_confirmation(user_input) and len(session.messages) >= 3

    if is_confirm:
        # Inject a system-level hint so Claude outputs clean text only
        session.messages[-1] = {
            "role": "user",
            "content": f"{user_input}\n\n（確認されました。最終版をクリーンテキストのみで出力してください。ヘッダー・絵文字・日本語確認版・区切り線は不要です。eBayにそのままコピペできる状態で。）",
        }

    try:
        response = _get_client().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=session.messages,
        )
        reply = response.content[0].text
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        reply = "エラーが発生しました。もう一度お試しください。"
        # Remove the failed user message
        session.messages.pop()
        return reply, session

    session.messages.append({"role": "assistant", "content": reply})

    if is_confirm:
        session.finalized = True

    return reply, session
