from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.deps import current_user
from app.models.user import User
from app.schemas.ai import (
    AudioRequest,
    AudioResponse,
    WritingScoreRequest,
    WritingScoreResponse,
    SpeakingScoreResponse,
)
from app.services import ai_service

router = APIRouter()


@router.post("/score-writing", response_model=WritingScoreResponse)
def score_writing(
    body: WritingScoreRequest,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
):
    from app.models.question import Question

    question = db.query(Question).filter(Question.id == body.question_id).first()
    prompt = (
        question.content.get("prompt", "Write an essay.")
        if question
        else "Write an essay."
    )
    return ai_service.score_writing(prompt, body.answer_text)


@router.post("/generate-audio", response_model=AudioResponse)
def generate_audio(
    body: AudioRequest,
    user: User = Depends(current_user),
):
    return ai_service.generate_audio(body.text, body.voice)


@router.post("/score-speaking", response_model=SpeakingScoreResponse)
def score_speaking(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    question_id: str = Form(...),
    topic: str = Form(...),
    speaking_points: str = Form(""),
    user: User = Depends(current_user),
):
    audio_bytes = audio.file.read()
    points = [p.strip() for p in speaking_points.split(",") if p.strip()]
    return ai_service.score_speaking(topic, points, audio_bytes)
