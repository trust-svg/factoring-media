from datetime import date
from pydantic import BaseModel, Field


class FlashcardCreate(BaseModel):
    front: str = Field(..., min_length=1, max_length=500)
    back: str = Field(..., min_length=1, max_length=500)
    source: str = "user"


class FlashcardOut(BaseModel):
    id: str
    front: str
    back: str
    source: str
    ease_factor: float
    interval_days: int
    repetitions: int
    due_date: date

    model_config = {"from_attributes": True}


class ReviewRequest(BaseModel):
    quality: int = Field(..., ge=1, le=5)


class MineRequest(BaseModel):
    words: list[dict]  # [{"front": "...", "back": "..."}]
