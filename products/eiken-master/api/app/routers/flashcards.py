from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models.flashcard import Flashcard
from app.models.user import User
from app.schemas.flashcard import (
    FlashcardCreate,
    FlashcardOut,
    ReviewRequest,
    MineRequest,
)
from app.services.sm2 import update_sm2

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
