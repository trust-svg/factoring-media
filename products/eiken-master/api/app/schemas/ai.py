from typing import Optional
from pydantic import BaseModel, Field


class WritingScoreRequest(BaseModel):
    session_id: str
    question_id: str
    answer_text: str = Field(..., min_length=1, max_length=5000)


class CriterionScore(BaseModel):
    score: float
    max: float
    comment: str


class WritingScoreResponse(BaseModel):
    score: float
    max_score: float
    feedback: str
    criteria: dict[str, CriterionScore]
    is_passing: bool


class SpeakingScoreResponse(WritingScoreResponse):
    transcript: str


class AudioRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str = "alloy"


class AudioResponse(BaseModel):
    audio_base64: str
    duration_hint_seconds: Optional[float] = None


class PraiseRequest(BaseModel):
    skill: str
    is_passing: bool
    score_pct: float  # 0.0-1.0
    streak: int = 0


class PraiseResponse(BaseModel):
    praise: str


class ExplainJaRequest(BaseModel):
    question: str
    choices: list[str]
    answer_index: int
    explanation: str
    passage: Optional[str] = None


class ExplainJaResponse(BaseModel):
    question_ja: str
    passage_ja: Optional[str] = None
    choices_ja: list[str]
    answer_ja: str
    explanation_ja: str


class VocabHintRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=200)


class VocabHintResponse(BaseModel):
    reading: str
    meaning: str
    example: str
