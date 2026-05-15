# products/eiken-master/api/tests/test_sm2.py
from dataclasses import dataclass
from datetime import date, timedelta

from app.services.sm2 import SM2Card, update_sm2


@dataclass
class _Card(SM2Card):
    repetitions: int = 0
    interval_days: int = 1
    ease_factor: float = 2.5
    due_date: date = None

    def __post_init__(self):
        if self.due_date is None:
            self.due_date = date.today()


def test_quality_below_3_resets_repetitions():
    card = _Card(repetitions=3, interval_days=10, ease_factor=2.5)
    result = update_sm2(card, quality=2)
    assert result.repetitions == 0
    assert result.interval_days == 1
    assert result.due_date == date.today() + timedelta(days=1)


def test_quality_3_first_review_sets_interval_1():
    card = _Card(repetitions=0, interval_days=1, ease_factor=2.5)
    result = update_sm2(card, quality=3)
    assert result.interval_days == 1
    assert result.repetitions == 1


def test_quality_4_second_review_sets_interval_6():
    card = _Card(repetitions=1, interval_days=1, ease_factor=2.5)
    result = update_sm2(card, quality=4)
    assert result.interval_days == 6
    assert result.repetitions == 2


def test_quality_5_third_review_multiplies_interval():
    card = _Card(repetitions=2, interval_days=6, ease_factor=2.5)
    result = update_sm2(card, quality=5)
    assert result.interval_days == round(6 * 2.5)
    assert result.repetitions == 3


def test_ease_factor_increases_on_quality_5():
    card = _Card(repetitions=1, interval_days=1, ease_factor=2.5)
    result = update_sm2(card, quality=5)
    # 2.5 + 0.1 - (5-5)*0.08 = 2.6
    assert abs(result.ease_factor - 2.6) < 0.001


def test_ease_factor_decreases_on_quality_3():
    card = _Card(repetitions=1, interval_days=1, ease_factor=2.5)
    result = update_sm2(card, quality=3)
    # 2.5 + 0.1 - (5-3)*0.08 = 2.5 + 0.1 - 0.16 = 2.44
    assert abs(result.ease_factor - 2.44) < 0.001


def test_ease_factor_never_below_1_3():
    card = _Card(repetitions=1, interval_days=1, ease_factor=1.3)
    result = update_sm2(card, quality=1)
    assert result.ease_factor >= 1.3
