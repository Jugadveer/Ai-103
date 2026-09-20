"""Intent and entity extraction accuracy."""
import pytest

from app.core.nlu import parse


@pytest.mark.parametrize("text,intent", [
    # water, several phrasings and units
    ("I drank 3 glasses of water", "log_water"),
    ("drank two glasses", "log_water"),
    ("had 4 cups", "log_water"),
    ("I had 1.5 litres today", "log_water"),
    # sleep
    ("I slept 6 hours", "log_sleep"),
    ("slept 7.5", "log_sleep"),
    ("got 5 hours of sleep", "log_sleep"),
    # food
    ("I ate a sandwich 400 calories", "log_meal"),
    ("lunch was about 650 kcal", "log_meal"),
    # activity
    ("I walked 5000 steps", "log_steps"),
    ("did 30 minutes of yoga", "log_exercise"),
    ("worked out 45 mins", "log_exercise"),
    ("I ran 30 minutes", "log_exercise"),
    # vitals
    ("my weight is 70 kg", "log_vital_weight"),
    ("height 175 cm", "log_vital_height"),
    ("my heart rate is 72", "log_vital_hr"),
    ("pulse 88 bpm", "log_vital_hr"),
    ("blood pressure 130/85", "log_vital_bp"),
    ("bp is 120 over 80", "log_vital_bp"),
    # mood
    ("my mood is 6 out of 10", "log_mood"),
    ("feeling 3/10 today", "log_mood"),
    # keyword intents
    ("how am I doing today?", "checkin"),
    ("show me the patterns", "insights"),
    ("make a summary for my doctor", "report"),
    ("I took my medicine", "log_medication_taken"),
    ("what can you do", "help"),
])
def test_intent_classification(text, intent):
    assert parse(text)["intent"] == intent, f"misread: {text!r}"


@pytest.mark.parametrize("text,field,value", [
    ("I drank 3 glasses of water", "water_glasses", 3),
    ("I had 1.5 litres today", "water_glasses", 6),   # 1.5L -> 6 glasses
    ("drank two glasses", "water_glasses", 2),        # word number
    ("I slept 6.5 hours", "sleep_hours", 6.5),
    ("I walked 5000 steps", "steps", 5000),
    ("did 30 minutes of yoga", "exercise_mins", 30),
    ("my weight is 70 kg", "weight_kg", 70),
    ("my mood is 6 out of 10", "mood_score", 6),
])
def test_entity_extraction(text, field, value):
    assert parse(text)["entities"][field] == value


def test_blood_pressure_extracts_both_numbers():
    e = parse("blood pressure 130/85")["entities"]
    assert e["systolic"] == 130 and e["diastolic"] == 85


def test_drank_is_not_mistaken_for_ran():
    """Regression: 'ran' matched inside 'd-ran-k' and logged exercise."""
    assert parse("I drank 3 glasses of water")["intent"] == "log_water"


def test_questions_do_not_log_values():
    """'How many glasses should I drink' must not log 'glasses'."""
    for q in ["how many glasses should I drink",
              "what is my sleep average",
              "how much water do I need"]:
        assert parse(q)["intent"] == "question", f"would have logged: {q!r}"


def test_unrecognised_message_is_unknown():
    result = parse("I have a headache")
    assert result["intent"] == "unknown"
    assert result["confidence"] == 0.0


def test_empty_input_is_safe():
    assert parse("")["intent"] == "unknown"
    assert parse(None)["intent"] == "unknown"


def test_meal_item_is_extracted():
    assert "sandwich" in parse("I ate a sandwich 400 calories")["entities"]["item"]


def test_confidence_is_reported():
    assert parse("I slept 6 hours")["confidence"] >= 0.5
    assert parse("qwertyuiop")["confidence"] == 0.0
