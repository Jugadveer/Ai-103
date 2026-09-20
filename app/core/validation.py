"""
Bounds checking for every health value the app accepts.

A user who types "I slept 500 hours" should get a clear correction, not a
corrupted sleep average. Every range below has a stated reason so the
numbers are defensible rather than arbitrary.
"""
from app.core.errors import ValidationError

# field -> (minimum, maximum, unit, why this range)
RANGES = {
    "water_glasses":  (1, 30, "glasses", "30 glasses (~7L) is past safe intake"),
    "calories":       (1, 5000, "kcal", "a single logged item above 5000 kcal is a typo"),
    "sleep_hours":    (0.5, 18, "hours", "over 18 hours in one night is implausible"),
    "steps":          (1, 100000, "steps", "100k steps is beyond ultramarathon distance"),
    "exercise_mins":  (1, 600, "minutes", "10 hours of exercise in a day is implausible"),
    "weight_kg":      (20, 300, "kg", "outside plausible adult body weight"),
    "heart_rate":     (30, 220, "bpm", "outside physiologically possible resting range"),
    "systolic":       (60, 260, "mmHg", "outside measurable blood pressure range"),
    "diastolic":      (30, 160, "mmHg", "outside measurable blood pressure range"),
    "mood_score":     (1, 10, "out of 10", "mood is recorded on a 1-10 scale"),
    "height_cm":      (100, 250, "cm", "outside plausible adult height"),
    "age":            (13, 120, "years", "outside the range this app is built for"),
}


def check_number(field: str, value) -> float:
    """Validate a numeric health value. Returns it, or raises ValidationError."""
    if field not in RANGES:
        raise ValidationError(f"Unknown field '{field}'.", field, value)

    low, high, unit, reason = RANGES[field]

    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"I couldn't read '{value}' as a number.", field, value
        )

    if num != num or num in (float("inf"), float("-inf")):
        raise ValidationError(f"'{value}' is not a usable number.", field, value)

    if num < low or num > high:
        raise ValidationError(
            f"{num:g} {unit} looks wrong - I accept {low:g} to {high:g} {unit}. "
            f"({reason}.)",
            field, value,
        )
    return num


def check_text(field: str, value: str, max_len: int = 500) -> str:
    """Validate a free-text field: non-empty and length-capped."""
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"The {field} can't be empty.", field, value)
    if len(text) > max_len:
        raise ValidationError(
            f"That's too long - please keep it under {max_len} characters.",
            field, value,
        )
    return text


def bmi(weight_kg: float, height_cm: float) -> float:
    """Body mass index, rounded to one decimal."""
    height_m = check_number("height_cm", height_cm) / 100
    return round(check_number("weight_kg", weight_kg) / (height_m ** 2), 1)


def bmi_band(value: float) -> str:
    """Standard adult BMI band. Informational only - not a diagnosis."""
    if value < 18.5:
        return "below the healthy range"
    if value < 25:
        return "in the healthy range"
    if value < 30:
        return "above the healthy range"
    return "well above the healthy range"
