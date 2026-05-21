from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models.flashcard import Flashcard
from app.models.user import User
from app.schemas.flashcard import (
    ExampleResponse,
    FlashcardCreate,
    FlashcardOut,
    ReviewRequest,
    MineRequest,
)
from app.services.sm2 import update_sm2
from app.services import ai_service

router = APIRouter()


@router.get("/due", response_model=list[FlashcardOut])
def get_due_cards(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    cards = (
        db.query(Flashcard)
        .filter(Flashcard.user_id == user.id, Flashcard.due_date <= today)
        .order_by(Flashcard.due_date)
        .limit(50)
        .all()
    )
    return cards


@router.post("/", response_model=FlashcardOut, status_code=201)
def create_flashcard(
    body: FlashcardCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    card = Flashcard(user_id=user.id, **body.model_dump())
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.post("/{card_id}/review", response_model=FlashcardOut)
def review_flashcard(
    card_id: str,
    body: ReviewRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    card = (
        db.query(Flashcard)
        .filter(Flashcard.id == card_id, Flashcard.user_id == user.id)
        .first()
    )
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    update_sm2(card, body.quality)
    db.commit()
    db.refresh(card)
    return card


@router.post("/{card_id}/generate-example", response_model=ExampleResponse)
def generate_example(
    card_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    card = (
        db.query(Flashcard)
        .filter(Flashcard.id == card_id, Flashcard.user_id == user.id)
        .first()
    )
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if card.example:
        return ExampleResponse(example=card.example, example_ja=card.example_ja)
    try:
        result = ai_service.generate_flashcard_example(card.front, card.back)
    except Exception:
        raise HTTPException(status_code=502, detail="Example generation failed")
    card.example = result["example"]
    card.example_ja = result.get("example_ja")
    db.commit()
    return ExampleResponse(example=card.example, example_ja=card.example_ja)


@router.post("/seed-vocab")
def seed_vocab(
    grade: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.data.eiken_vocab import EIKEN_VOCAB_PRE2, EIKEN_VOCAB_2

    if grade not in ("pre2", "2"):
        raise HTTPException(status_code=400, detail="grade must be 'pre2' or '2'")
    vocab = EIKEN_VOCAB_PRE2 if grade == "pre2" else EIKEN_VOCAB_2
    created = 0
    for word, meaning in vocab:
        exists = (
            db.query(Flashcard)
            .filter(Flashcard.user_id == user.id, Flashcard.front == word)
            .first()
        )
        if not exists:
            db.add(
                Flashcard(user_id=user.id, front=word, back=meaning, source="builtin")
            )
            created += 1
    db.commit()
    return {"created": created}


@router.post("/mine", status_code=201)
def mine_words(
    body: MineRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    created = 0
    for w in body.words:
        front = w.get("front", "").strip()
        back = w.get("back", "").strip()
        if not front or not back:
            continue
        exists = (
            db.query(Flashcard)
            .filter(Flashcard.user_id == user.id, Flashcard.front == front)
            .first()
        )
        if not exists:
            card = Flashcard(user_id=user.id, front=front, back=back, source="mined")
            db.add(card)
            created += 1
    db.commit()
    return {"created": created}
