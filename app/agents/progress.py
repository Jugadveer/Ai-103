"""
Progress agent - streaks, daily goals and achievements.

A meta-agent: it stores nothing of its own. It asks every specialist for
its report and turns those facts into the things that keep a person coming
back. Every number here is derived from real logged data, so nothing shown
to the user is decorative.
"""
from app.agents.base import BaseAgent, AgentReply
from app.store import db

NON_DATA_AGENTS = ("coach", "insights", "report", "progress")

# Five daily goals. Hitting one is a "ring closed".
GOALS = [
    {"key": "water",    "label": "Hydration", "target": 8,
     "unit": "glasses",
     "read": lambda p: p.get("hydration", {}).get("glasses_today", 0)},
    {"key": "sleep",    "label": "Sleep",     "target": 7,
     "unit": "hours",
     "read": lambda p: p.get("sleep", {}).get("last_night", 0)},
    {"key": "steps",    "label": "Steps",     "target": 8000,
     "unit": "steps",
     "read": lambda p: p.get("activity", {}).get("steps_today", 0)},
    {"key": "active",   "label": "Movement",  "target": 30,
     "unit": "minutes",
     "read": lambda p: p.get("activity", {}).get("minutes_today", 0)},
    {"key": "nutrition", "label": "Meals",    "target": 3,
     "unit": "meals",
     "read": lambda p: p.get("nutrition", {}).get("meals_today", 0)},
]

# Each achievement states the real condition behind it, so it can be
# explained rather than just displayed.
ACHIEVEMENTS = [
    {"key": "first_step",  "name": "First Step",
     "how": "Log anything at all",
     "test": lambda c: c["days_logged"] >= 1},
    {"key": "hydrated",    "name": "Well Watered",
     "how": "Reach 8 glasses in a single day",
     "test": lambda c: c["best_water"] >= 8},
    {"key": "rested",      "name": "Properly Rested",
     "how": "Sleep 7 hours or more in one night",
     "test": lambda c: c["best_sleep"] >= 7},
    {"key": "mover",       "name": "On the Move",
     "how": "Reach 150 active minutes in a week",
     "test": lambda c: c["active_week"] >= 150},
    {"key": "streak_3",    "name": "Three in a Row",
     "how": "Log something three days running",
     "test": lambda c: c["streak"] >= 3},
    {"key": "streak_7",    "name": "Full Week",
     "how": "Log something seven days running",
     "test": lambda c: c["streak"] >= 7},
    {"key": "full_picture", "name": "Full Picture",
     "how": "Close every ring in one day",
     "test": lambda c: c["rings_closed"] == len(GOALS)},
    {"key": "self_aware",  "name": "Self Aware",
     "how": "Record your mood on seven different days",
     "test": lambda c: c["mood_days"] >= 7},
    {"key": "on_schedule", "name": "On Schedule",
     "how": "Take every tracked medication for a full day",
     "test": lambda c: c["meds_tracked"] > 0 and c["meds_pending"] == 0},
]

POINTS_PER_RING = 10
POINTS_PER_STREAK_DAY = 5
POINTS_PER_ACHIEVEMENT = 25
LEVEL_STEP = 100


class ProgressAgent(BaseAgent):
    name = "progress"
    description = (
        "Tracks daily goals, logging streaks and achievements, all derived "
        "from real logged data."
    )

    def handle(self, query: str) -> AgentReply:
        # A question about the subject deserves an answer, not this
        # agent's analysis. "Why do streaks help with habits" is not a
        # request for the current streak.
        spoken = self.try_answer(query)
        if spoken:
            return AgentReply(agent=self.name, text=spoken,
                              data={"answered": True})

        f = self.report()
        if f["days_logged"] == 0:
            return AgentReply(
                agent=self.name,
                text="Nothing logged yet. Log one thing and you have a streak.",
                data=f,
            )

        closed = f["rings_closed"]
        text = (f"You are on a {f['streak']}-day streak and have closed "
                f"{closed} of {len(GOALS)} rings today.")
        if f["unlocked_today"]:
            text += (" You just unlocked "
                     + ", ".join(a["name"] for a in f["unlocked_today"]) + ".")
        elif closed < len(GOALS):
            nxt = next((g for g in f["goals"] if not g["done"]), None)
            if nxt:
                text += (f" The closest one left is {nxt['label']}: "
                         f"{nxt['remaining']:g} more {nxt['unit']}.")
        return AgentReply(agent=self.name, text=text, data=f)

    # -----------------------------------------------------------------

    def _peers(self) -> dict:
        if not self.bus:
            return {}
        return self.bus.broadcast(self.name, reason="progress scan",
                                  exclude=NON_DATA_AGENTS)

    def report(self) -> dict:
        peers = self._peers()

        goals = []
        for g in GOALS:
            current = g["read"](peers) or 0
            done = current >= g["target"]
            goals.append({
                "key": g["key"], "label": g["label"], "unit": g["unit"],
                "current": current, "target": g["target"], "done": done,
                "remaining": max(0, g["target"] - current),
                "percent": min(100, round(100 * current / g["target"])),
            })
        rings_closed = sum(1 for g in goals if g["done"])

        streak, longest, days_logged = self._streaks()
        counters = {
            "days_logged": days_logged,
            "streak": streak,
            "rings_closed": rings_closed,
            "best_water": self._best("water", "glasses"),
            "best_sleep": self._best("sleep", "hours"),
            "active_week": peers.get("activity", {}).get("minutes_week", 0),
            "mood_days": peers.get("mood", {}).get("days_logged", 0),
            "meds_tracked": peers.get("medication", {}).get("tracked", 0),
            "meds_pending": len(peers.get("medication", {}).get("pending", [])),
        }

        unlocked, locked = [], []
        for a in ACHIEVEMENTS:
            entry = {"key": a["key"], "name": a["name"], "how": a["how"]}
            (unlocked if a["test"](counters) else locked).append(entry)

        points = (rings_closed * POINTS_PER_RING
                  + streak * POINTS_PER_STREAK_DAY
                  + len(unlocked) * POINTS_PER_ACHIEVEMENT)

        return {
            "has_data": days_logged > 0,
            "goals": goals,
            "rings_closed": rings_closed,
            "rings_total": len(GOALS),
            "streak": streak,
            "longest_streak": longest,
            "days_logged": days_logged,
            "unlocked": unlocked,
            "locked": locked,
            "unlocked_today": [],
            "points": points,
            "level": 1 + points // LEVEL_STEP,
            "points_into_level": points % LEVEL_STEP,
            "points_per_level": LEVEL_STEP,
            "status": "ok" if streak else "idle",
        }

    def _best(self, table: str, column: str) -> float:
        rows = db.query(
            f"SELECT MAX(total) m FROM "
            f"(SELECT SUM({column}) total FROM {table} GROUP BY day)")
        return rows[0]["m"] or 0 if rows else 0

    def _streaks(self) -> tuple[int, int, int]:
        """Current streak, longest streak, and total days with any log."""
        days = db.logged_days()
        if not days:
            return 0, 0, 0

        # Current streak counts back from today, or from yesterday if today
        # has nothing yet - a day is not "broken" until it has ended.
        current = 0
        start = 0 if db.today() in days else 1
        offset = start
        while db.days_ago(offset) in days:
            current += 1
            offset += 1

        ordered = sorted(days)
        longest = run = 1
        for prev, nxt in zip(ordered, ordered[1:]):
            from datetime import date, timedelta
            gap = date.fromisoformat(nxt) - date.fromisoformat(prev)
            run = run + 1 if gap == timedelta(days=1) else 1
            longest = max(longest, run)

        return current, longest, len(days)
