import base64
import json
import os
import tempfile
from typing import Any

from app.config import ANTHROPIC_API_KEY, OPENAI_API_KEY
from app.schemas.ai import (
    AudioResponse,
    CriterionScore,
    SpeakingScoreResponse,
    WritingScoreResponse,
)

# Module-level client references — initialised lazily on first use so that
# importing this module does not trigger the Anthropic/OpenAI SDK at startup
# (avoids issues when credentials sub-packages are sandboxed in tests).
anthropic_client: Any = None
openai_client: Any = None


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


_WRITING_PROMPT = """\
You are an Eiken exam evaluator. Grade the following English writing response.

Scoring criteria:
- content (0-4 points): Does it address the prompt with relevant ideas?
- grammar (0-3 points): Are sentences grammatically correct?
- vocabulary (0-3 points): Is vocabulary varied and appropriate?

Prompt: {prompt}
Student answer: {answer}

Return JSON only (no markdown):
{{"score": <0-10>, "feedback": "<2-3 sentences in Japanese>", "criteria": {{"content": {{"score": <0-4>, "max": 4, "comment": "<Japanese>"}}, "grammar": {{"score": <0-3>, "max": 3, "comment": "<Japanese>"}}, "vocabulary": {{"score": <0-3>, "max": 3, "comment": "<Japanese>"}}}}}}
"""

_SPEAKING_PROMPT = """\
You are an Eiken exam evaluator. The student was asked to speak on a topic.

Topic: {topic}
Speaking points: {points}
Transcribed speech: {transcript}

Scoring criteria:
- content (0-4 points): Does it address the topic with relevant ideas?
- fluency (0-3 points): Is speech coherent and sufficiently developed?
- grammar (0-3 points): Are sentences grammatically correct?

Return JSON only (no markdown):
{{"score": <0-10>, "feedback": "<2-3 sentences in Japanese>", "criteria": {{"content": {{"score": <0-4>, "max": 4, "comment": "<Japanese>"}}, "fluency": {{"score": <0-3>, "max": 3, "comment": "<Japanese>"}}, "grammar": {{"score": <0-3>, "max": 3, "comment": "<Japanese>"}}}}}}
"""


def _parse_criteria(raw: dict) -> dict[str, CriterionScore]:
    try:
        return {k: CriterionScore(**v) for k, v in raw.items()}
    except (TypeError, Exception) as e:
        raise ValueError(f"Unexpected criteria structure: {raw}") from e


def score_writing(prompt: str, answer: str) -> WritingScoreResponse:
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": _WRITING_PROMPT.format(prompt=prompt, answer=answer),
            }
        ],
    )
    try:
        data = json.loads(msg.content[0].text)
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


def generate_audio(text: str, voice: str = "alloy") -> AudioResponse:
    resp = _get_openai().audio.speech.create(model="tts-1", voice=voice, input=text)
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
    msg = _get_anthropic().messages.create(
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
    try:
        data = json.loads(msg.content[0].text)
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
あなたは英検コーチです。以下のデータをもとに、学習者への短いアドバイスを2文以内の日本語で返してください。
励ましと、最も弱いスキルへの具体的な改善アドバイスを含めてください。
回答はアドバイス文のみ（JSONや箇条書き不要）。

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
日常的な場面の短い会話や説明を想定した問題です。
以下のJSON形式で返してください（他のテキスト不要）:
{{
  "question": "状況・設問（英語）例: 'A girl is talking to her teacher. What does she want to do?'",
  "choices": ["選択肢A（英語）", "選択肢B（英語）", "選択肢C（英語）", "選択肢D（英語）"],
  "answer": 0,
  "explanation": "正答の解説（日本語、2〜3文）"
}}
answerは0〜3の正答インデックス。選択肢は4つ。""",
    "writing": """\
英検{grade_label}レベルのライティング問題を1問生成してください。
以下のJSON形式で返してください（他のテキスト不要）:
{{
  "prompt": "英作文の課題（英語）例: 'Do you think ... ? Write about 80 words.'",
  "min_words": 80,
  "example_response": "模範解答（英語、80〜100語）"
}}
課題は賛否を問うもの（Do you agree...? / Do you think...?）で。""",
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
    prompt = _QUESTION_PROMPTS[skill].format(
        grade_label=_GRADE_LABELS.get(grade, grade)
    )
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
あなたは英検コーチです。学習者が今セッションを完了しました。以下のデータを参考に、\
1〜2文の温かい日本語で褒めてください。具体的な数字（スコアや連続日数）を使い、\
自信が持てる言葉で締めてください。文章のみで返してください。

技能: {skill_ja}
結果: {result}（スコア {score_pct}%）
連続学習日数: {streak}日
"""

_PRAISE_STREAK_PROMPT = """\
あなたは英検コーチです。学習者の進捗をほめる1〜2文の日本語メッセージを返してください。\
連続学習日数や合格確率を具体的に使い、明るく励ましてください。文章のみ。

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
あなたは英検の日本語解説担当の先生です。中学生向けに、以下の英語問題の解説を日本語で書いてください。

問題: {question}
正答: {correct_answer}
英語の解説: {explanation}

以下のJSON形式のみで返してください（マークダウン不要）:
{{"answer_ja": "正答の日本語訳または意味（30文字以内）", "explanation_ja": "なぜこの答えが正しいかの日本語解説（中学生向け、2〜3文）"}}
"""


def explain_in_japanese(
    question: str, choices: list[str], answer_index: int, explanation: str
) -> dict:
    correct_answer = choices[answer_index] if answer_index < len(choices) else ""
    msg = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": _EXPLAIN_JA_PROMPT.format(
                    question=question,
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
