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
