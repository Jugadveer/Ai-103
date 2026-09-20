"""
Energy requirement estimates.

Mifflin-St Jeor for resting metabolic rate, multiplied by a standard
activity factor to reach a daily maintenance figure. This is the equation
dietitians use as a starting point, and it is arithmetic on numbers the
user gave us, not a measurement and not a medical judgement.

It is an ESTIMATE. Published error for Mifflin-St Jeor is roughly ten
percent either way for most adults, and considerably worse at the
extremes of body composition. Everything that consumes these numbers says
so.
"""

# Standard multipliers applied to resting rate. The wording is what the
# user picks from, so it has to describe a week rather than a day.
ACTIVITY_LEVELS = {
    "sedentary": (1.2, "Desk-bound, little deliberate exercise"),
    "light": (1.375, "Light exercise one to three days a week"),
    "moderate": (1.55, "Moderate exercise three to five days a week"),
    "active": (1.725, "Hard exercise six or seven days a week"),
    "very_active": (1.9, "Physical job, or training twice a day"),
}

DEFAULT_LEVEL = "light"

# How far from maintenance counts as worth mentioning. Day-to-day intake
# swings are normal; a persistent gap is the thing worth naming.
NOTABLE_GAP = 0.15        # 15 percent
LARGE_GAP = 0.30          # 30 percent

# Below this, an intake figure is more likely to be incomplete logging
# than a real fast, so the assessment says that instead of alarming.
IMPLAUSIBLY_LOW = 0.45    # 45 percent of maintenance


def resting_rate(weight_kg: float, height_cm: float, age: int,
                 sex: str) -> float:
    """Mifflin-St Jeor resting metabolic rate, in kcal per day."""
    base = (10 * weight_kg) + (6.25 * height_cm) - (5 * age)
    if (sex or "").lower().startswith("m"):
        return base + 5
    if (sex or "").lower().startswith("f"):
        return base - 161
    # Not stated: use the midpoint rather than assuming, and say so upstream.
    return base - 78


def maintenance(weight_kg: float, height_cm: float, age: int, sex: str,
                activity_level: str = DEFAULT_LEVEL) -> dict:
    """Daily maintenance estimate with the working shown."""
    rmr = resting_rate(weight_kg, height_cm, age, sex)
    factor, label = ACTIVITY_LEVELS.get(
        activity_level, ACTIVITY_LEVELS[DEFAULT_LEVEL])
    total = rmr * factor
    return {
        "resting": int(round(rmr)),
        "activity_factor": factor,
        "activity_label": label,
        "maintenance": int(round(total)),
        # A plausible band rather than a single number, because the
        # equation is not precise enough to justify one.
        "range_low": int(round(total * 0.9)),
        "range_high": int(round(total * 1.1)),
    }


def balance(intake: int, maintenance_kcal: int) -> dict:
    """Where an intake sits relative to maintenance, and how notable that is."""
    if maintenance_kcal <= 0:
        return {"gap": 0, "ratio": 0.0, "verdict": "unknown"}

    gap = intake - maintenance_kcal
    ratio = intake / maintenance_kcal

    if ratio < IMPLAUSIBLY_LOW:
        verdict = "under_logged"
    elif ratio < 1 - LARGE_GAP:
        verdict = "well_under"
    elif ratio < 1 - NOTABLE_GAP:
        verdict = "under"
    elif ratio > 1 + LARGE_GAP:
        verdict = "well_over"
    elif ratio > 1 + NOTABLE_GAP:
        verdict = "over"
    else:
        verdict = "around"

    return {
        "gap": int(round(gap)),
        "ratio": round(ratio, 2),
        "verdict": verdict,
        "percent": int(round(abs(1 - ratio) * 100)),
    }


VERDICT_WORDS = {
    "under_logged": "far below maintenance, which usually means the day is "
                    "only part-logged rather than genuinely that low",
    "well_under": "well below maintenance",
    "under": "below maintenance",
    "around": "close to maintenance",
    "over": "above maintenance",
    "well_over": "well above maintenance",
    "unknown": "impossible to place without your height, weight and age",
}
