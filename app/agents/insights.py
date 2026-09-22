"""
Insights agent - a meta-agent.

It holds no data of its own. It asks every other agent for its report and
looks for relationships between domains that no single agent can see. This
is cross-agent communication used for analysis rather than for answering a
single question.

Every insight it returns carries the evidence it was derived from, so a
claim can always be traced back to real logged numbers.
"""
from app.agents.base import BaseAgent, AgentReply
from app.store import db




# How much agreement counts as "moving together", and how many days it
# takes to say so.
#
# Fourteen, not seven. Over one week the seeded sleep and mood series
# correlate at -0.55, over two at 0.25 and over four at 0.74. The
# relationship is a trend, and a week of it is mostly noise pointing
# whichever way the last bad night pointed. Claiming a link from seven
# days would be the kind of statistics this app should not be doing.
MOVE_TOGETHER = 0.45
MIN_PAIRED_DAYS = 14


def correlate(a: dict | None, b: dict | None) -> dict | None:
    """
    Pearson correlation of two agents' days, over the days they share.

    Returns None when there is not enough overlap, or when either series
    never varies: a flat week has no correlation to report, and dividing
    by its zero spread would invent one.
    """
    if not a or not b:
        return None
    days = sorted(set(a) & set(b))
    n = len(days)
    if n < MIN_PAIRED_DAYS:
        return None

    xs = [float(a[d]) for d in days]
    ys = [float(b[d]) for d in days]
    mx, my = sum(xs) / n, sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    top = sum(p * q for p, q in zip(dx, dy))
    spread = (sum(p * p for p in dx) * sum(q * q for q in dy)) ** 0.5
    if spread == 0:
        return None
    return {"r": round(top / spread, 2), "days": n}


class InsightsAgent(BaseAgent):
    name = "insights"
    description = (
        "Correlates data across every other agent to surface patterns, "
        "each with the evidence behind it."
    )
    holds_data = False

    def handle(self, query: str) -> AgentReply:
        # A question about the subject deserves an answer, not this
        # agent's analysis. "Why do streaks help with habits" is not a
        # request for the current streak.
        peers = self.bus.broadcast(
            self.name, reason="correlation scan",
        ) if self.bus else {}

        # Every peer's report is exactly the grounding a general question
        # wants, and it has already been gathered.
        spoken = self.try_answer(query, peers)
        if spoken:
            return AgentReply(agent=self.name, text=spoken,
                              data={"answered": True})

        found = self.find_patterns(peers)

        if not found:
            text = ("Nothing stands out across your logs yet. Keep logging for "
                    "a few more days and patterns become easier to spot.")
        else:
            lines = [f"{i}. {p['insight']} ({p['evidence']})"
                     for i, p in enumerate(found, 1)]
            text = "Here's what connects across your data:\n" + "\n".join(lines)

        return AgentReply(agent=self.name, text=text,
                          data={"patterns": found, "peers": peers})

    def find_patterns(self, peers: dict) -> list[dict]:
        """Rule-based correlation. Each rule states its own evidence."""
        out = []
        sleep = peers.get("sleep", {})
        mood = peers.get("mood", {})
        water = peers.get("hydration", {})
        food = peers.get("nutrition", {})
        move = peers.get("activity", {})
        meds = peers.get("medication", {})

        def has(domain: dict) -> bool:
            """A domain only counts if something was actually logged."""
            return bool(domain.get("has_data"))

        # Sleep <-> mood is the best-established everyday link, and the
        # headline finding of the whole project, so it is worth measuring
        # rather than inferring.
        #
        # This used to fire when the sleep agent said "poor" and the mood
        # agent said "low", which is two independent threshold crossings
        # and not what "tracking alongside" means. It was also brittle in
        # a way that only showed up on the day: the mood cutoff is an
        # average of 4 or below, the seeded month averaged 4.1, and the
        # insight vanished. A demo's headline should not turn on a tenth
        # of a point, or on which side of a fortnight the weekends land.
        #
        # So: line the two agents' own days up against each other and
        # measure whether they actually move together. Both series come
        # over the bus from the agent that owns them.
        link = correlate(sleep.get("by_day"), mood.get("by_day"))
        if (link and link["days"] >= MIN_PAIRED_DAYS
                and link["r"] >= MOVE_TOGETHER
                and has(sleep) and sleep.get("avg_hours", 99) < sleep.get("target", 7)):
            out.append({
                "insight": "Your mood is tracking alongside your sleep",
                "evidence": f"across {link['days']} days they move together "
                            f"(r={link['r']}), averaging "
                            f"{sleep.get('avg_hours')}h sleep and "
                            f"mood {mood.get('avg_score')}/10",
                "agents": ["sleep", "mood"],
            })

        # Sedentary + poor sleep reinforce each other.
        if (has(sleep) and sleep.get("status") == "poor"
                and move.get("status") == "sedentary"):
            out.append({
                "insight": "Low activity and poor sleep tend to reinforce "
                           "each other - daytime movement helps night-time sleep",
                "evidence": f"{move.get('minutes_week')} active minutes this "
                            f"week, {sleep.get('avg_hours')}h average sleep",
                "agents": ["activity", "sleep"],
            })

        # Under-eating plus under-drinking is a common fatigue combination.
        if ((has(food) or has(water)) and food.get("status") == "low"
                and water.get("status") == "low"):
            out.append({
                "insight": "You're running low on both food and fluids today",
                "evidence": f"{food.get('calories_today')} kcal and "
                            f"{water.get('glasses_today')} glasses so far",
                "agents": ["nutrition", "hydration"],
            })

        # Sleep debt accumulating over the week.
        if has(sleep) and sleep.get("debt_hours", 0) >= 7:
            out.append({
                "insight": "You've built up more than a full night of sleep debt",
                "evidence": f"{sleep.get('debt_hours')}h short across "
                            f"{sleep.get('nights_logged')} nights",
                "agents": ["sleep"],
            })

        # Missed medication is worth surfacing plainly.
        if has(meds) and meds.get("status") == "missed":
            out.append({
                "insight": f"Medication still pending today: "
                           f"{', '.join(meds.get('pending', []))}",
                "evidence": f"{meds.get('adherence_week_pct')}% adherence "
                            f"this week",
                "agents": ["medication"],
            })

        # Repeated symptoms alongside any poor domain.
        symptom_count = peers.get("symptom", {}).get("count", 0)
        if symptom_count >= 3:
            weak = [n for n, d in peers.items()
                    if isinstance(d, dict) and
                    d.get("status") in ("low", "poor", "sedentary")]
            if weak:
                out.append({
                    "insight": f"You've logged {symptom_count} symptoms while "
                               f"{', '.join(weak)} are all below target",
                    "evidence": "repeated symptoms alongside multiple low domains",
                    "agents": ["symptom"] + weak,
                })

        return out

    def report(self) -> dict:
        return {"role": "analysis", "holds_data": False}
