import base64
import json
import logging
import os
import tempfile
import time
from typing import Any

from app.config import ANTHROPIC_API_KEY, OPENAI_API_KEY
from app.schemas.ai import (
    AudioResponse,
    CriterionScore,
    SpeakingScoreResponse,
    WritingScoreResponse,
)

logger = logging.getLogger(__name__)

# Module-level client references — initialised lazily on first use so that
# importing this module does not trigger the Anthropic/OpenAI SDK at startup
# (avoids issues when credentials sub-packages are sandboxed in tests).
anthropic_client: Any = None
openai_client: Any = None


def _strip_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) that Claude occasionally adds."""
    import re

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _safe_json_loads(text: str) -> dict:
    """Parse JSON from Claude response, repairing common formatting issues."""
    text = _strip_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Claude sometimes embeds literal newlines/tabs inside JSON string values.
        # Replace unescaped control characters so the JSON becomes parseable.
        import re

        repaired = re.sub(r"(?<!\\)\n", " ", text)
        repaired = re.sub(r"(?<!\\)\r", "", repaired)
        repaired = re.sub(r"(?<!\\)\t", " ", repaired)
        return json.loads(repaired)


def _call_with_retry(fn, max_retries: int = 2, initial_delay: float = 2.0):
    """Call fn() with retry on transient Anthropic API errors (5xx / connection)."""
    import anthropic

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except (anthropic.InternalServerError, anthropic.APIConnectionError) as e:
            last_exc = e
            if attempt < max_retries:
                delay = initial_delay * (2**attempt)
                logger.warning(
                    "Anthropic transient error attempt %d/%d, retrying in %.0fs: %s",
                    attempt + 1,
                    max_retries + 1,
                    delay,
                    e,
                )
                time.sleep(delay)
        except Exception:
            raise  # non-transient errors (auth, bad request, etc.) — don't retry
    raise last_exc


def _get_anthropic():
    global anthropic_client
    if anthropic_client is None:
        from anthropic import Anthropic

        anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return anthropic_client


def _get_openai():
    global openai_client
    if openai_client is None:
        from openai import OpenAI

        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return openai_client


_OWL_PERSONA = """\
あなたはフクロウ博士です。丸い眼鏡をかけた元気でかわいい白いフクロウで、中学生に英語をやさしく教えているよ！
「ホーホー！」「なるほどね！」「大丈夫だよ！」「いっしょに頑張ろうね！」などの明るくかわいい口調を使ってね。
「じゃ」「のじゃ」などの古い言い方はしないよ。むずかしい言葉は使わず、やさしい日本語でね。
"""

_WRITING_PROMPT = (
    _OWL_PERSONA
    + """\
英検の採点委員として、以下の英作文を採点してください。

採点基準:
- content（0〜4点）: 課題に合った内容かどうか
- grammar（0〜3点）: 文法が正しいかどうか
- vocabulary（0〜3点）: 語彙が豊かで適切かどうか

課題: {prompt}
生徒の回答: {answer}

JSONのみで返してください（マークダウン不要）。feedbackとcommentはフクロウ博士の口調で書いてね！:
{{"score": <0-10>, "feedback": "<フクロウ博士の口調で2〜3文の日本語フィードバック>", "criteria": {{"content": {{"score": <0-4>, "max": 4, "comment": "<フクロウ博士の口調で日本語>"}}, "grammar": {{"score": <0-3>, "max": 3, "comment": "<フクロウ博士の口調で日本語>"}}, "vocabulary": {{"score": <0-3>, "max": 3, "comment": "<フクロウ博士の口調で日本語>"}}}}}}
"""
)

_SPEAKING_PROMPT = (
    _OWL_PERSONA
    + """\
英検の採点委員として、スピーキングを採点してください。

トピック: {topic}
スピーキングのポイント: {points}
文字起こし: {transcript}

採点基準:
- content（0〜4点）: トピックに合った内容かどうか
- fluency（0〜3点）: 話し方が流暢でまとまっているか
- grammar（0〜3点）: 文法が正しいかどうか

JSONのみで返してください（マークダウン不要）。feedbackとcommentはフクロウ博士の口調で書いてね！:
{{"score": <0-10>, "feedback": "<フクロウ博士の口調で2〜3文の日本語フィードバック>", "criteria": {{"content": {{"score": <0-4>, "max": 4, "comment": "<フクロウ博士の口調で日本語>"}}, "fluency": {{"score": <0-3>, "max": 3, "comment": "<フクロウ博士の口調で日本語>"}}, "grammar": {{"score": <0-3>, "max": 3, "comment": "<フクロウ博士の口調で日本語>"}}}}}}
"""
)


def _parse_criteria(raw: dict) -> dict[str, CriterionScore]:
    try:
        return {k: CriterionScore(**v) for k, v in raw.items()}
    except (TypeError, Exception) as e:
        raise ValueError(f"Unexpected criteria structure: {raw}") from e


def score_writing(prompt: str, answer: str) -> WritingScoreResponse:
    msg = _call_with_retry(
        lambda: _get_anthropic().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": _WRITING_PROMPT.format(prompt=prompt, answer=answer),
                }
            ],
        )
    )
    try:
        data = _safe_json_loads(msg.content[0].text)
        score = float(data["score"])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise ValueError(
            f"Unexpected Claude response: {msg.content[0].text[:200]}"
        ) from e
    return WritingScoreResponse(
        score=score,
        max_score=10.0,
        feedback=data["feedback"],
        criteria=_parse_criteria(data["criteria"]),
        is_passing=score >= 6.0,
    )


def generate_flashcard_example(front: str, back: str) -> dict:
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
        messages=[
            {
                "role": "user",
                "content": (
                    f"英検準2・2級レベルの単語「{front}」（意味: {back}）を使った、\n"
                    "自然で短い英語の例文を1つ作ってください。\n"
                    "次のJSON形式のみで返してください（マークダウン不要）:\n"
                    '{"example": "英語の例文", "example_ja": "その例文の自然な日本語訳"}'
                ),
            }
        ],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text.strip())
    return {
        "example": data.get("example", ""),
        "example_ja": data.get("example_ja", ""),
    }


def generate_audio(text: str, voice: str = "alloy") -> AudioResponse:
    resp = _call_with_retry(
        lambda: _get_openai().audio.speech.create(
            model="tts-1", voice=voice, input=text
        )
    )
    return AudioResponse(audio_base64=base64.b64encode(resp.content).decode())


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    with tempfile.NamedTemporaryFile(
        suffix=os.path.splitext(filename)[1], delete=False
    ) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            resp = _get_openai().audio.transcriptions.create(
                model="whisper-1", file=(filename, f, "audio/webm")
            )
        return resp.text
    finally:
        os.unlink(tmp_path)


def score_speaking(
    topic: str, speaking_points: list[str], audio_bytes: bytes
) -> SpeakingScoreResponse:
    transcript = transcribe_audio(audio_bytes)
    msg = _call_with_retry(
        lambda: _get_anthropic().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": _SPEAKING_PROMPT.format(
                        topic=topic,
                        points=", ".join(speaking_points),
                        transcript=transcript,
                    ),
                }
            ],
        )
    )
    try:
        data = _safe_json_loads(msg.content[0].text)
        score = float(data["score"])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise ValueError(
            f"Unexpected Claude response: {msg.content[0].text[:200]}"
        ) from e
    return SpeakingScoreResponse(
        score=score,
        max_score=10.0,
        feedback=data["feedback"],
        criteria=_parse_criteria(data["criteria"]),
        is_passing=score >= 6.0,
        transcript=transcript,
    )


_ADVICE_PROMPT = """\
あなたはフクロウ博士です。丸い眼鏡をかけた元気でかわいい白いフクロウ先生だよ！
「ホーホー！」「なるほどね！」「大丈夫だよ！」などの明るくかわいい口調で、2文以内の日本語アドバイスを返してね。
励ましと、最も弱いスキルへの具体的な改善アドバイスを含めてね。回答はアドバイス文のみ（JSONや箇条書き不要）。

目標: 英検{grade}
試験まで: {days}日
合格確率: {prob}
スキル別正答率（直近2週間）:
  リーディング: {reading}
  リスニング: {listening}
  ライティング: {writing}
  スピーキング: {speaking}
連続学習日数: {streak}日
"""


_QUESTION_PROMPTS = {
    "reading": """\
英検{grade_label}レベルのリーディング問題を1問生成してください。
以下のJSON形式で返してください（他のテキスト不要）:
{{
  "passage": "英文パッセージ（120〜160語）",
  "question": "設問（英語）",
  "choices": ["選択肢A", "選択肢B", "選択肢C", "選択肢D"],
  "answer": 0,
  "explanation": "正答の解説（日本語、2〜3文）"
}}
answerは0〜3の正答インデックス。選択肢は4つ。パッセージは完全な英文で。""",
    "listening": """\
英検{grade_label}レベルのリスニング問題を1問生成してください。
日常的な場面の短い会話または説明文を作り、その内容に関する設問にしてください。

【重要】毎回異なるシナリオにすること:
- 登場人物: Tom, Emma, Mike, Lisa, David, Anna, Kevin, Yuki, Chris, Maya など、毎回変えること（Sarah は使わない）
- 場面: 学校・図書館・スーパー・駅・病院・公園・オフィス・レストラン・カフェ・旅行など多様に
- 質問タイプ: What / When / Where / Why / How / Who など偏らず変化させること

以下のJSON形式で返してください（他のテキスト不要）:
{{
  "conversation": "実際に読み上げる会話または説明文（英語）。会話なら 'A: ... B: ...' 形式、説明文なら平文で。80〜120語程度。",
  "question": "設問（英語）例: 'What does the woman decide to do?'",
  "choices": ["選択肢A（英語）", "選択肢B（英語）", "選択肢C（英語）", "選択肢D（英語）"],
  "answer": 0,
  "explanation": "正答の解説（日本語、2〜3文）"
}}
answerは0〜3の正答インデックス。選択肢は4つ。""",
    "writing_pre2": """\
英検準2級レベルのライティング問題を1問生成してください。
以下のJSON形式で返してください（他のテキスト不要）:
{{
  "prompt": "英作文の課題（英語）例: 'Do you think students should ... ? Write about 50 words.'",
  "min_words": 50,
  "example_response": "模範解答（英語、50〜60語）"
}}
課題は中学生〜高校生が身近に感じる話題で、賛否を問う形式（Do you agree...? / Do you think...?）。""",
    "writing_2": """\
英検2級レベルのライティング問題を1問生成してください。
以下のJSON形式で返してください（他のテキスト不要）:
{{
  "prompt": "英作文の課題（英語）例: 'Do you think ... ? Write about 80 to 100 words. Use TWO of the following POINTS: [Point1] / [Point2] / [Point3]'",
  "points": ["観点A（英語）", "観点B（英語）", "観点C（英語）"],
  "min_words": 80,
  "example_response": "模範解答（英語、80〜100語。2つの観点を含む）"
}}
課題は社会・環境・テクノロジーなど高校生〜社会人向けのテーマで、賛否を問う形式。観点を3つ提示し生徒が2つ選んで使う形式にする。""",
    "speaking": """\
英検{grade_label}レベルのスピーキング問題を1問生成してください。
以下のJSON形式で返してください（他のテキスト不要）:
{{
  "topic": "スピーキングのトピック（英語、疑問文）",
  "speaking_points": ["観点1（英語）", "観点2（英語）"],
  "time_limit_seconds": 60
}}
トピックは身近な話題で意見を述べやすいものを。""",
}

_GRADE_LABELS = {"pre2": "準2級", "2": "2級"}


def generate_question(skill: str, grade: str) -> dict:
    key = f"writing_{grade}" if skill == "writing" else skill
    prompt = _QUESTION_PROMPTS[key].format(grade_label=_GRADE_LABELS.get(grade, grade))
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


_PRAISE_PROMPT = """\
あなたはフクロウ博士です。丸い眼鏡をかけた元気でかわいい白いフクロウ先生だよ！
学習者が今セッションを完了したよ！以下のデータを参考に、1〜2文の温かい日本語で褒めてね。
「ホーホー！」「すごいね！」「やったね！」などフクロウ博士らしい口調で、具体的な数字を使い、自信が持てる言葉で締めてね。文章のみで返してね。

技能: {skill_ja}
結果: {result}（スコア {score_pct}%）
連続学習日数: {streak}日
"""

_PRAISE_STREAK_PROMPT = """\
あなたはフクロウ博士です。丸い眼鏡をかけた元気でかわいい白いフクロウ先生だよ！
学習者の進捗をフクロウ博士らしいかわいい口調で1〜2文の日本語メッセージで褒めてね。\
連続学習日数や合格確率を具体的に使い、「ホーホー！」「すごいね！」など明るく励ましてね。文章のみ。

連続学習日数: {streak}日
合格確率: {prob}
目標: 英検{grade_label}
"""

_SKILL_JA = {
    "reading": "リーディング",
    "listening": "リスニング",
    "writing": "ライティング",
    "speaking": "スピーキング",
}


def generate_praise_for_result(
    skill: str, is_passing: bool, score_pct: float, streak: int
) -> str:
    result_str = "合格ライン達成" if is_passing else "惜しい！もう少し"
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[
            {
                "role": "user",
                "content": _PRAISE_PROMPT.format(
                    skill_ja=_SKILL_JA.get(skill, skill),
                    result=result_str,
                    score_pct=round(score_pct * 100),
                    streak=streak,
                ),
            }
        ],
    )
    return msg.content[0].text.strip()


def generate_praise_for_progress(
    grade: str, streak: int, pass_probability: float | None
) -> str:
    grade_label = "準2級" if grade == "pre2" else "2級"
    prob_str = (
        f"{round(pass_probability * 100)}%"
        if pass_probability is not None
        else "計測中"
    )
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[
            {
                "role": "user",
                "content": _PRAISE_STREAK_PROMPT.format(
                    streak=streak,
                    prob=prob_str,
                    grade_label=grade_label,
                ),
            }
        ],
    )
    return msg.content[0].text.strip()


_VOCAB_HINT_PROMPT = """\
あなたは英語辞書アシスタントです。以下の英単語またはフレーズについて、中学生向けに簡潔に説明してください。

単語/フレーズ: {word}

以下のJSON形式のみで返してください（マークダウン不要）:
{{"reading": "カタカナ読み（なければ空文字）", "meaning": "日本語の意味（20文字以内）", "example": "短い英語の例文（なければ空文字）"}}
"""


def get_vocab_hint(word: str) -> dict:
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": _VOCAB_HINT_PROMPT.format(word=word)}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


_EXPLAIN_JA_PROMPT = """\
あなたはフクロウ博士です。丸い眼鏡をかけた元気でかわいい白いフクロウで、中学生に英語をやさしく教えているよ！
「ホーホー！」「なるほどね！」「いっしょに覚えようね！」「覚えてね！」「大丈夫だよ！」などの明るくかわいい口調を使ってね。
「じゃ」「のじゃ」などの古い言い方はしないよ。元気で親しみやすい話し方でね！
むずかしい言葉は使わず、わかりやすい日本語で説明してね。

{passage_section}問題: {question}

選択肢:
{choices_block}

正解: {correct_letter}. {correct_answer}
英語の解説: {explanation}

以下のJSON形式のみで返してください（マークダウン不要）:
{{
  "question_ja": "問題文のわかりやすい日本語訳（中学生が読んでスッと理解できる言葉で）",
  "passage_ja": "英文の日本語訳（パッセージがない場合は null。むずかしい単語には（）でよみがなや説明を添える）",
  "choices_ja": ["選択肢Aの自然な日本語訳", "Bの日本語訳", "Cの日本語訳", "Dの日本語訳"],
  "answer_ja": "正解の日本語訳（10〜20文字程度で簡潔に）",
  "explanation_ja": "フクロウ博士のかわいい口調で説明してね。「ホーホー！」から始めて、なぜこれが正解なのかを1〜2文で説明し、他の選択肢がなぜちがうかを1文で説明し、「いっしょに覚えようね！」と言ってこの問題の大事な単語や表現を1つ取り上げて説明してね。全部で4〜5文、元気でかわいいフクロウ博士の口調で！"
}}
"""

_CHOICE_LETTERS = ["A", "B", "C", "D"]


def explain_in_japanese(
    question: str,
    choices: list[str],
    answer_index: int,
    explanation: str,
    passage: str | None = None,
) -> dict:
    correct_answer = choices[answer_index] if answer_index < len(choices) else ""
    correct_letter = _CHOICE_LETTERS[answer_index] if answer_index < 4 else "A"
    choices_block = "\n".join(
        f"{_CHOICE_LETTERS[i]}. {c}" for i, c in enumerate(choices)
    )
    passage_section = f"英語パッセージ:\n{passage}\n\n" if passage else ""
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=900,
        messages=[
            {
                "role": "user",
                "content": _EXPLAIN_JA_PROMPT.format(
                    passage_section=passage_section,
                    question=question,
                    choices_block=choices_block,
                    correct_letter=correct_letter,
                    correct_answer=correct_answer,
                    explanation=explanation,
                ),
            }
        ],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text.strip())
    # ensure choices_ja has 4 elements
    cja = data.get("choices_ja", [])
    while len(cja) < len(choices):
        cja.append("")
    data["choices_ja"] = cja[: len(choices)]
    return data


# ── AI Error Categorization ──────────────────────────────────────────────────

_ERROR_CATEGORY_PROMPTS = {
    "reading": """\
英検リーディング問題で学習者が誤答しました。最も当てはまるエラーカテゴリを1つだけ返してください。

問題: {question}
パッセージ: {passage}

カテゴリ（このうち1つだけ返す、他のテキスト不要）:
vocab_unknown | grammar_structure | inference_required | main_idea | detail_misread""",
    "listening": """\
英検リスニング問題で学習者が誤答しました。最も当てはまるエラーカテゴリを1つだけ返してください。

問題: {question}

カテゴリ（このうち1つだけ返す、他のテキスト不要）:
vocab_unknown | inference_required | detail_missed | context_misread""",
}

_VALID_CATEGORIES = {
    "reading": {
        "vocab_unknown",
        "grammar_structure",
        "inference_required",
        "main_idea",
        "detail_misread",
    },
    "listening": {
        "vocab_unknown",
        "inference_required",
        "detail_missed",
        "context_misread",
    },
    "writing": {
        "grammar_verb",
        "grammar_preposition",
        "vocab_choice",
        "cohesion",
        "word_count",
    },
    "speaking": {"pronunciation", "fluency", "content_coverage", "grammar"},
}


def categorize_error(skill: str, question_content: dict) -> str:
    """Classify wrong-answer error type using Claude. Returns a category string."""
    if skill not in _ERROR_CATEGORY_PROMPTS:
        return f"{skill}_error"
    prompt_tpl = _ERROR_CATEGORY_PROMPTS[skill]
    question = question_content.get("question", "")
    passage = question_content.get("passage", "")
    prompt = prompt_tpl.format(question=question, passage=passage)
    try:
        msg = _get_anthropic().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        result = msg.content[0].text.strip().split()[0]
        valid = _VALID_CATEGORIES.get(skill, set())
        return result if result in valid else f"{skill}_error"
    except Exception:
        return f"{skill}_error"


_DAILY_PLAN_PROMPT = """\
あなたはフクロウ博士です。丸い眼鏡をかけた元気でかわいい白いフクロウ先生だよ！
以下のデータをもとに、今日の学習タスクリストをJSONで返してね。messageはフクロウ博士の口調でね！

目標: 英検{grade_label}
試験まで: {days}日
1日の目標学習時間: {daily_minutes}分（週4日のみ勉強）
最近の技能別正答率:
  リーディング: {reading}
  リスニング: {listening}
  ライティング: {writing}
  スピーキング: {speaking}

英検の試験構造（重要）:
- 一次試験（筆記）: リーディング・リスニング・ライティングの3技能
- 二次試験（面接）: スピーキングのみ（一次合格者だけが受ける）
- まず一次合格を優先すること

時間配分ルール:
1. 合計時間が {daily_minutes} 分以内に収まるようにする
2. 弱い技能（正答率が低いもの）に多く時間を割く
   - 60%未満 → 最優先（20〜25分）
   - 60〜75% → 優先（15〜20分）
   - 75%以上 → 維持（10〜15分）
3. データなしの技能は60%未満扱いで最優先する
4. 単語カード（flashcards）を毎日10分含める
5. 残り日数が20日以内はspeakingも必ず5〜10分含める

description（演習内容）の書き方（重要）:
- アプリの実際の動作に合わせて書くこと（問題数はminutesから自動計算される）
- reading: 4択長文問題を複数問解く → 「長文読解・全問正解を目指す」「精読→選択肢を丁寧に吟味」
- listening: 4択音声問題を複数問解く → 「音声を聞いて4択で答える」「細部まで集中して聴く」
- writing: 英作文1問→Claude AI採点 → 「英作文1問・AI採点でフィードバック確認」
- speaking: スピーキング1問→録音→AI採点 → 「スピーチ録音→AI採点で発音・内容確認」
- flashcards: due カード全件 → 「単語カード復習・曖昧なものを重点確認」
- 30字以内、学習のポイントが伝わる言葉で書くこと

以下のJSON形式のみで返してください（マークダウン不要）:
{{
  "message": "今日の学習への一言アドバイス（日本語、1〜2文）",
  "tasks": [
    {{"skill": "reading|listening|writing|speaking|flashcards", "description": "具体的な演習内容（30字以内）", "minutes": 10}},
    ...
  ]
}}
"""


def generate_daily_plan(
    grade: str,
    days_remaining: int | None,
    daily_minutes: int,
    skill_breakdown: dict,
) -> dict:
    def fmt(v: float | None) -> str:
        return f"{round(v * 100)}%" if v is not None else "データなし"

    grade_label = "準2級" if grade == "pre2" else "2級"
    days_str = f"{days_remaining}" if days_remaining is not None else "未設定"
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": _DAILY_PLAN_PROMPT.format(
                    grade_label=grade_label,
                    days=days_str,
                    daily_minutes=daily_minutes,
                    reading=fmt(skill_breakdown.get("reading")),
                    listening=fmt(skill_breakdown.get("listening")),
                    writing=fmt(skill_breakdown.get("writing")),
                    speaking=fmt(skill_breakdown.get("speaking")),
                ),
            }
        ],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def generate_advice(
    grade: str,
    days_remaining: int | None,
    pass_probability: float | None,
    skill_breakdown: dict,
    streak: int,
) -> str:
    def fmt(v: float | None) -> str:
        return f"{round(v * 100)}%" if v is not None else "データなし"

    grade_label = "準2級" if grade == "pre2" else "2級"
    days_str = f"{days_remaining}" if days_remaining is not None else "未設定"
    prob_str = fmt(pass_probability)

    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[
            {
                "role": "user",
                "content": _ADVICE_PROMPT.format(
                    grade=grade_label,
                    days=days_str,
                    prob=prob_str,
                    reading=fmt(skill_breakdown.get("reading")),
                    listening=fmt(skill_breakdown.get("listening")),
                    writing=fmt(skill_breakdown.get("writing")),
                    speaking=fmt(skill_breakdown.get("speaking")),
                    streak=streak,
                ),
            }
        ],
    )
    return msg.content[0].text.strip()
