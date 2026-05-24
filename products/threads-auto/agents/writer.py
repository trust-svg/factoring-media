from __future__ import annotations

"""③ ライター — 投稿の自動生成エージェント

品質スコア自己採点 + 類似度チェック + パターン強制ローテーション
"""

import json
import logging
import random
from difflib import SequenceMatcher
from typing import Any

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    KNOWLEDGE_DIR,
    QUALITY_THRESHOLD,
    SIMILARITY_THRESHOLD,
)
from state_manager import (
    add_to_queue,
    get_post_history,
    get_analyst_feedback,
    get_research_cache,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
BATCH_SIZE = 10
RECENT_PATTERN_LOOKBACK = 3
RECENT_THEME_LOOKBACK = 3


def _load_knowledge() -> dict[str, Any]:
    """ナレッジファイルを全て読み込む"""
    files = [
        "persona.json",
        "theme_tree.json",
        "post_patterns.json",
        "hook_lines.json",
        "ng_words.json",
    ]
    knowledge: dict[str, Any] = {}
    for f in files:
        path = KNOWLEDGE_DIR / f
        if path.exists():
            knowledge[f.replace(".json", "")] = json.loads(
                path.read_text(encoding="utf-8")
            )
    return knowledge


def _get_recent_patterns(
    history: list[dict], n: int = RECENT_PATTERN_LOOKBACK
) -> list[str]:
    """直近n件の投稿パターンIDを取得"""
    return [p.get("pattern_id", "") for p in history[-n:] if p.get("pattern_id")]


def _get_recent_themes(
    history: list[dict], n: int = RECENT_THEME_LOOKBACK
) -> list[str]:
    """直近n件のテーマを取得"""
    return [p.get("theme", "") for p in history[-n:] if p.get("theme")]


def _check_similarity(
    new_text: str, history: list[dict], threshold: float = SIMILARITY_THRESHOLD
) -> bool:
    """過去投稿との類似度チェック。True = 類似しすぎ（棄却すべき）"""
    for past in history:
        past_text = past.get("text", "")
        if not past_text:
            continue
        ratio = SequenceMatcher(None, new_text, past_text).ratio()
        if ratio >= threshold:
            logger.warning(
                "類似度 %.2f >= %.2f: 棄却 | %s", ratio, threshold, new_text[:50]
            )
            return True
    return False


def _check_ng_words(text: str, ng_words: dict) -> bool:
    """NGワードチェック。True = NGワードあり（棄却すべき）"""
    for word in ng_words.get("hard_ng", []):
        if word in text:
            logger.warning("NGワード検出: %s", word)
            return True
    return False


def _build_prompt(
    knowledge: dict[str, Any],
    history: list[dict],
    feedback: dict,
    research: list[dict],
    batch_size: int,
) -> str:
    """ライター用のプロンプトを構築"""
    persona = knowledge.get("persona", {})
    patterns = knowledge.get("post_patterns", {}).get("patterns", [])
    hooks = knowledge.get("hook_lines", {}).get("hooks", [])

    recent_patterns = _get_recent_patterns(history)
    recent_themes = _get_recent_themes(history)

    # 使用可能なパターンをフィルタ
    available_patterns = [p for p in patterns if p["id"] not in recent_patterns]
    if not available_patterns:
        available_patterns = patterns  # 全部使った場合はリセット

    # ランダムにピックアップ（多様性のため）
    selected_patterns = random.sample(
        available_patterns, min(batch_size, len(available_patterns))
    )

    # リサーチネタ（最新20件）
    recent_research = research[-20:] if research else []

    prompt = f"""あなたはThreads投稿のプロライターです。以下のアカウント設定に従って投稿を{batch_size}本生成してください。

## アカウント設定
- アカウント名: {persona.get("account_name", "")}
- ジャンル: {persona.get("genre", "")}
- ターゲット: {json.dumps(persona.get("target", {}), ensure_ascii=False)}
- 口調: {json.dumps(persona.get("tone", {}), ensure_ascii=False)}

## 使用する投稿パターン（各投稿で異なるパターンを使うこと）
{json.dumps(selected_patterns, ensure_ascii=False, indent=2)}

## 1行目のフック参考（構造だけ参考にして、丸パクリはNG）
{json.dumps(hooks[:4], ensure_ascii=False, indent=2)}

## 避けるべきテーマ（直近で使用済み）
{json.dumps(recent_themes, ensure_ascii=False)}

## アナリストからのフィードバック
{json.dumps(feedback.get("directives", []), ensure_ascii=False)}

## リサーチネタ（参考にしてOK）
{json.dumps(recent_research, ensure_ascii=False, indent=2)}

## 生成ルール
1. 各投稿は500文字以内
2. 各投稿で異なるパターンと異なるテーマを使う
3. 1行目は必ずフックとして機能させる（スクロールを止める力）
4. {batch_size}本中1本はアフィリエイト投稿（post_typeを"affiliate"に設定）
5. アフィリエイト投稿の場合、pr_commentフィールドにPRコメントを入れる
6. アフィリエイト投稿では投稿テーマに合わせて以下から最適なリンクを選び、affiliate_linkフィールドに設定する:
   - 転職エージェント活用・年収交渉・担当者選びがテーマ → "https://career.trustmedialab.com/go"（転職AGENT Navi）
   - 企業研究・年収情報・面接対策・クチコミ確認がテーマ → "https://career.trustmedialab.com/go2"（ワンキャリア転職）

## パターン配分（重要 — データ分析に基づく必須ルール）
10本のバッチでは、以下の配分を厳守すること:
- warning型（警告型）: 2本 — 平均195viewsで最も伸びるパターン
- before_after型: 2本 — 平均153viewsで2番目に強い
- comment_bait型（コメント誘導型）: 2本 — リプライ獲得がThreadsアルゴリズム上最重要
- thread_tree型（ツリー展開型）: 1本 — エンゲージメント率が最高
- expose型（暴露系）: 1本 — ただし過去投稿と同じネタは絶対に使うな
- その他（list_tips, hot_take, number_fact, confession等）: 2本
- empathy_first型・cta_simple型は使わない（パフォーマンスが低い）

## 重複ネタ禁止ルール（最重要）
以下のネタは既に複数回使っているため、絶対に使うな:
- 「転職エージェントの紹介料は年収の30%」→ 4回使用済み。二度と使うな
- 「御社の理念に共感しました」は落ちる → 2回使用済み
- 「3年は同じ会社にいないと不利は嘘」→ 2回使用済み
毎回新しい具体的エピソードや切り口を使うこと。抽象的な話ではなく、具体的な場面・数字・体験を毎回変えること。

## 自己採点（各投稿につけること）
以下10項目を各10点満点で採点:
1. hook_strength: 1行目のフックの強さ
2. usefulness: 有益性（読者が得るもの）
3. specificity: 具体性（数字、エピソード）
4. tempo: テンポ感（読みやすさ）
5. persona_match: ペルソナとの一致度
6. originality: 独自性
7. emotion: 感情の揺さぶり
8. actionability: 行動を促す力
9. shareability: シェアしたくなるか
10. controversy: 議論を呼ぶ力（賛否が分かれるか）

## 出力形式（JSON配列）
```json
[
  {{
    "text": "投稿本文",
    "pattern_id": "使用したパターンID",
    "theme": "テーマ名",
    "post_type": "normal|comment_bait|thread_tree|affiliate",
    "comment_text": "コメント誘導型の場合の続き（nullable）",
    "pr_comment": "アフィリエイト投稿の場合のPRコメント（nullable）",
    "affiliate_link": "アフィリエイト投稿の場合のリンクURL（nullableだがaffiliate型では必須）",
    "thread_texts": ["ツリー型の場合の返信テキスト配列（nullable）"],
    "scores": {{
      "hook_strength": 8,
      "usefulness": 7,
      ...
    }},
    "avg_score": 7.5
  }}
]
```

JSON配列のみを返してください。説明文は不要です。
"""
    return prompt


async def generate_posts(batch_size: int = BATCH_SIZE) -> list[dict]:
    """投稿をバッチ生成し、品質チェックを通過したものだけ返す"""
    knowledge = _load_knowledge()
    history = get_post_history(limit=100)
    feedback = get_analyst_feedback()
    research = get_research_cache()

    prompt = _build_prompt(knowledge, history, feedback, research, batch_size)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    approved_posts: list[dict] = []
    ng_words = knowledge.get("ng_words", {})

    for attempt in range(1 + MAX_RETRIES):
        remaining = batch_size - len(approved_posts)
        if remaining <= 0:
            break

        if attempt > 0:
            logger.info("リトライ %d/%d: 残り%d本生成", attempt, MAX_RETRIES, remaining)
            prompt_suffix = f"\n\n追加で{remaining}本生成してください。前回棄却された投稿とは異なる内容にしてください。"
        else:
            prompt_suffix = ""

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt + prompt_suffix}],
            )
            content = response.content[0].text.strip()

            # JSON部分を抽出
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            posts = json.loads(content)
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.error("生成結果のパースに失敗: %s", e)
            continue
        except anthropic.APIError as e:
            logger.error("Claude API エラー: %s", e)
            break

        for post in posts:
            text = post.get("text", "")
            avg_score = post.get("avg_score", 0)

            # 品質スコアチェック
            if avg_score < QUALITY_THRESHOLD:
                logger.info(
                    "品質スコア %.1f < %.1f: 棄却 | %s",
                    avg_score,
                    QUALITY_THRESHOLD,
                    text[:50],
                )
                continue

            # NGワードチェック
            if _check_ng_words(text, ng_words):
                continue

            # 類似度チェック（過去投稿 + 今回の承認済み投稿）
            combined_history = history + approved_posts
            if _check_similarity(text, combined_history):
                continue

            # 文字数チェック
            if len(text) > 500:
                logger.info("文字数超過 (%d > 500): 棄却", len(text))
                continue

            approved_posts.append(post)
            if len(approved_posts) >= batch_size:
                break

    logger.info("生成完了: %d/%d本が品質チェック通過", len(approved_posts), batch_size)
    return approved_posts


async def run() -> None:
    """ライターエージェントのメインエントリ"""
    logger.info("=== ライター起動 ===")
    posts = await generate_posts()
    if posts:
        add_to_queue(posts)
        logger.info("%d本をキューに追加", len(posts))
    else:
        logger.warning("品質チェックを通過した投稿が0本でした")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
