# products/eiken-master/api/app/services/sm2.py
from datetime import date, timedelta
from typing import Protocol


class SM2Card(Protocol):
    repetitions: int
    interval_days: int
    ease_factor: float
    due_date: date


def update_sm2(card: SM2Card, quality: int) -> SM2Card:
    """SM-2アルゴリズム。quality: 1=全忘 2=誤答 3=ヒント正解 4=正解 5=即答"""
    if quality < 3:
        card.repetitions = 0
        card.interval_days = 1
    else:
        if card.repetitions == 0:
            card.interval_days = 1
        elif card.repetitions == 1:
            card.interval_days = 6
        else:
            card.interval_days = round(card.interval_days * card.ease_factor)
        card.repetitions += 1

    card.ease_factor = max(1.3, card.ease_factor + 0.1 - (5 - quality) * 0.08)
    card.due_date = date.today() + timedelta(days=card.interval_days)
    return card
