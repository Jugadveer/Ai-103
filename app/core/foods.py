"""
Food calorie reference.

Every figure here is an APPROXIMATE typical serving, gathered from public
nutrition labels and standard portion tables. They are estimates, not
measurements, and the interface says so wherever a number is shown.

This file is a calorie REFERENCE only. It does not decide what to ask the
user: that judgement belongs to the model in app/services/food_ai.py,
because any hand-written list of "vague" foods only knows what somebody
thought to write down. These figures ground the model where we hold them,
and stand alone as the offline fallback.
"""
import re

# name -> (kcal, typical portion description)
# Indian staples first, since that is the likely user.
FOODS: dict[str, tuple[int, str]] = {
    # --- Indian mains ---
    "roti": (110, "1 medium"), "chapati": (110, "1 medium"),
    "phulka": (85, "1 small"), "naan": (260, "1 plain"),
    "butter naan": (320, "1"), "paratha": (280, "1 plain"),
    "aloo paratha": (330, "1"), "puri": (140, "1"),
    "rice": (200, "1 cup cooked"), "jeera rice": (240, "1 cup"),
    "biryani": (490, "1 plate"), "chicken biryani": (540, "1 plate"),
    "veg biryani": (430, "1 plate"), "pulao": (330, "1 cup"),
    "dal": (150, "1 bowl"), "dal makhani": (280, "1 bowl"),
    "rajma": (210, "1 bowl"), "chole": (250, "1 bowl"),
    "paneer butter masala": (380, "1 bowl"), "palak paneer": (300, "1 bowl"),
    "shahi paneer": (390, "1 bowl"), "matar paneer": (310, "1 bowl"),
    "chicken curry": (300, "1 bowl"), "butter chicken": (440, "1 bowl"),
    "egg curry": (260, "1 bowl"), "fish curry": (250, "1 bowl"),
    "sambar": (140, "1 bowl"), "rasam": (70, "1 bowl"),
    "curd": (100, "1 bowl"), "raita": (90, "1 bowl"),

    # --- Indian breakfast and snacks ---
    "idli": (60, "1"), "dosa": (170, "1 plain"),
    "masala dosa": (290, "1"), "uttapam": (230, "1"),
    "vada": (140, "1"), "upma": (250, "1 bowl"),
    "poha": (210, "1 bowl"), "paneer tikka": (280, "1 plate"),
    "samosa": (260, "1"), "pakora": (180, "6 pieces"),
    "pav bhaji": (400, "1 plate"), "vada pav": (290, "1"),
    "chole bhature": (600, "1 plate"), "momos": (250, "6 steamed"),
    "maggi": (350, "1 packet"), "poori bhaji": (480, "1 plate"),

    # --- fast food ---
    "burger": (350, "1 regular"), "cheeseburger": (420, "1"),
    "big mac": (563, "1"), "mcchicken": (400, "1"),
    "mcaloo tikki": (330, "1"), "mcveggie": (400, "1"),
    "maharaja mac": (690, "1"), "mcspicy paneer": (500, "1"),
    "whopper": (660, "1"), "zinger burger": (450, "1"),
    "chicken burger": (430, "1"), "veg burger": (330, "1"),
    "fries": (330, "1 medium"), "large fries": (480, "1 large"),
    "small fries": (220, "1 small"),
    "pizza slice": (280, "1 slice"), "pizza": (850, "1 medium, 6 slices"),
    "garlic bread": (330, "4 pieces"),
    "sandwich": (300, "1"), "grilled sandwich": (350, "1"),
    "wrap": (390, "1"), "shawarma": (450, "1"),
    "hot dog": (300, "1"), "nuggets": (270, "6 pieces"),
    "fried chicken": (320, "2 pieces"),

    # --- drinks ---
    "water": (0, "any"), "black coffee": (5, "1 cup"),
    "coffee": (60, "1 cup with milk"), "tea": (50, "1 cup with milk"),
    "green tea": (2, "1 cup"), "milk": (120, "1 glass"),
    "coke": (140, "1 can"), "medium coke": (210, "1 medium"),
    "large coke": (310, "1 large"), "diet coke": (2, "1 can"),
    "pepsi": (150, "1 can"), "sprite": (140, "1 can"),
    "orange juice": (110, "1 glass"), "mango juice": (130, "1 glass"),
    "lassi": (180, "1 glass"), "sweet lassi": (220, "1 glass"),
    "buttermilk": (60, "1 glass"), "milkshake": (350, "1 glass"),
    "cold coffee": (220, "1 glass"), "beer": (150, "1 bottle"),

    # --- everyday western ---
    "toast": (80, "1 slice"), "bread": (75, "1 slice"),
    "butter toast": (140, "1 slice"), "omelette": (160, "2 eggs"),
    "boiled egg": (78, "1"), "fried egg": (90, "1"),
    "cereal": (200, "1 bowl with milk"), "oats": (160, "1 bowl"),
    "banana": (105, "1 medium"), "apple": (95, "1 medium"),
    "orange": (62, "1 medium"), "mango": (200, "1 medium"),
    "salad": (80, "1 bowl"), "pasta": (400, "1 plate"),
    "noodles": (380, "1 plate"), "fried rice": (400, "1 plate"),
    "soup": (120, "1 bowl"), "curd rice": (250, "1 bowl"),

    # --- sweets ---
    "gulab jamun": (150, "1"), "jalebi": (150, "1"),
    "rasgulla": (125, "1"), "laddu": (180, "1"),
    "barfi": (160, "1 piece"), "ice cream": (210, "1 scoop"),
    "chocolate": (230, "1 bar"), "biscuit": (50, "1"),
    "cake slice": (350, "1 slice"), "donut": (250, "1"),
    "brownie": (390, "1"),
}

# Quantity words, so "two rotis" is not read as one.
QUANTITY_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "half": 0.5, "couple": 2, "few": 3,
}

def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).strip()


def find(text: str) -> list[dict]:
    """
    Every food mentioned in a phrase, with quantity and estimated calories.

    Longest names are matched first so "butter chicken" wins over "chicken".
    """
    low = " " + _normalise(text) + " "
    found: list[dict] = []
    consumed: list[tuple[int, int]] = []

    for name in sorted(FOODS, key=len, reverse=True):
        # Allow a plural suffix so "two rotis" matches "roti".
        pattern = rf"(?<![a-z]){re.escape(name)}(?:es|s)?(?![a-z])"
        for match in re.finditer(pattern, low):
            span = match.span()
            if any(s <= span[0] < e or s < span[1] <= e for s, e in consumed):
                continue
            consumed.append(span)
            kcal, portion = FOODS[name]
            qty = _quantity_before(low, span[0])
            found.append({
                "name": name,
                "quantity": qty,
                "portion": portion,
                "kcal_each": kcal,
                "kcal": int(round(kcal * qty)),
            })

    found.sort(key=lambda f: low.index(f["name"]))
    return found


def _quantity_before(low: str, index: int) -> float:
    """Read a count immediately before a food name: '2 rotis', 'three idli'."""
    prefix = low[max(0, index - 14):index].strip().split()
    if not prefix:
        return 1
    last = prefix[-1]
    if last.isdigit():
        return min(20, int(last))
    return QUANTITY_WORDS.get(last, 1)


def total(items: list[dict]) -> int:
    return sum(i["kcal"] for i in items)


def describe(items: list[dict]) -> str:
    parts = []
    for i in items:
        qty = "" if i["quantity"] == 1 else f"{i['quantity']:g} x "
        parts.append(f"{qty}{i['name']} ({i['kcal']} kcal)")
    return ", ".join(parts)
