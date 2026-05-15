from typing import Any, Optional
from pydantic import BaseModel


class QuestionOut(BaseModel):
    id: str
    grade: str
    skill: str
    source: str
    content: Any
    audio_text: Optional[str] = None
    difficulty: float

    model_config = {"from_attributes": True}
