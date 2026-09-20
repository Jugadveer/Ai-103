"""Bounds checking on every health value."""
import pytest

from app.core.errors import ValidationError
from app.core.validation import RANGES, bmi, bmi_band, check_number, check_text


@pytest.mark.parametrize("field,value", [
    ("sleep_hours", 7.5), ("water_glasses", 8), ("calories", 650),
    ("steps", 9000), ("weight_kg", 70), ("heart_rate", 72),
    ("systolic", 120), ("mood_score", 6), ("height_cm", 175),
])
def test_plausible_values_accepted(field, value):
    assert check_number(field, value) == float(value)


@pytest.mark.parametrize("field,value", [
    ("sleep_hours", 500),      # implausible night
    ("sleep_hours", -3),       # negative
    ("water_glasses", 0),      # below minimum
    ("water_glasses", 999),    # dangerous intake
    ("calories", 99999),       # typo
    ("heart_rate", 5),         # not survivable
    ("mood_score", 50),        # off the 1-10 scale
    ("weight_kg", 2),          # not an adult weight
])
def test_implausible_values_rejected(field, value):
    with pytest.raises(ValidationError):
        check_number(field, value)


def test_non_numeric_rejected():
    with pytest.raises(ValidationError):
        check_number("sleep_hours", "eight-ish")


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        check_number("blood_type", 5)


def test_error_message_explains_the_range():
    with pytest.raises(ValidationError) as exc:
        check_number("sleep_hours", 40)
    msg = exc.value.user_message
    assert "0.5" in msg and "18" in msg


def test_every_range_is_internally_consistent():
    """Guards against a typo swapping a min and max."""
    for field, (low, high, unit, reason) in RANGES.items():
        assert low < high, f"{field} has min >= max"
        assert unit and reason, f"{field} is missing unit or reason"


def test_empty_text_rejected():
    with pytest.raises(ValidationError):
        check_text("symptom", "   ")


def test_overlong_text_rejected():
    with pytest.raises(ValidationError):
        check_text("symptom", "x" * 5000)


def test_bmi_calculation_and_band():
    assert bmi(70, 175) == 22.9
    assert bmi_band(22.9) == "in the healthy range"
    assert bmi_band(17) == "below the healthy range"
    assert bmi_band(27) == "above the healthy range"
    assert bmi_band(35) == "well above the healthy range"
