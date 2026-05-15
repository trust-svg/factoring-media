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
