import logging
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.deps import current_user
from app.models.user import User
from app.schemas.ai import (
    AudioRequest,
    AudioResponse,
    ExplainJaRequest,
    ExplainJaResponse,
    PraiseRequest,
    PraiseResponse,
    VocabHintRequest,
    VocabHintResponse,
    WritingScoreRequest,
    WritingScoreResponse,
    SpeakingScoreResponse,
)
from app.services import ai_service

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB — Whisper API limit


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
    try:
        return ai_service.score_writing(prompt, body.answer_text)
    except Exception:
        logger.exception("score_writing failed for question_id=%s", body.question_id)
        raise HTTPException(
            status_code=502, detail="AI scoring temporarily unavailable"
        )


@router.post("/generate-audio", response_model=AudioResponse)
def generate_audio(
    body: AudioRequest,
    user: User = Depends(current_user),
):
    try:
        return ai_service.generate_audio(body.text, body.voice)
    except Exception:
        logger.exception("generate_audio failed")
        raise HTTPException(
            status_code=502, detail="Audio generation temporarily unavailable"
        )


@router.post("/praise", response_model=PraiseResponse)
def praise(
    body: PraiseRequest,
    user: User = Depends(current_user),
):
    try:
        text = ai_service.generate_praise_for_result(
            skill=body.skill,
            is_passing=body.is_passing,
            score_pct=body.score_pct,
            streak=body.streak,
        )
        return PraiseResponse(praise=text)
    except Exception:
        logger.exception("praise failed for skill=%s", body.skill)
        raise HTTPException(
            status_code=502, detail="Praise generation temporarily unavailable"
        )


@router.post("/explain-ja", response_model=ExplainJaResponse)
def explain_ja(
    body: ExplainJaRequest,
    user: User = Depends(current_user),
):
    try:
        result = ai_service.explain_in_japanese(
            body.question, body.choices, body.answer_index, body.explanation
        )
        return ExplainJaResponse(**result)
    except Exception:
        logger.exception("explain_ja failed")
        raise HTTPException(
            status_code=502, detail="Japanese explanation temporarily unavailable"
        )


@router.post("/vocab-hint", response_model=VocabHintResponse)
def vocab_hint(
    body: VocabHintRequest,
    user: User = Depends(current_user),
):
    try:
        result = ai_service.get_vocab_hint(body.word)
        return VocabHintResponse(**result)
    except Exception:
        logger.exception("vocab_hint failed for word=%s", body.word)
        raise HTTPException(
            status_code=502, detail="Vocabulary hint temporarily unavailable"
        )


@router.post("/score-speaking", response_model=SpeakingScoreResponse)
def score_speaking(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    question_id: str = Form(...),
    topic: str = Form(...),
    speaking_points: List[str] = Form(default=[]),
    user: User = Depends(current_user),
):
    audio_bytes = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 25MB)")
    points = [p.strip() for p in speaking_points if p.strip()]
    try:
        return ai_service.score_speaking(topic, points, audio_bytes)
    except Exception:
        logger.exception("score_speaking failed for topic=%s", topic)
        raise HTTPException(
            status_code=502, detail="Speech scoring temporarily unavailable"
        )
