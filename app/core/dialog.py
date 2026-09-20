"""
Multi-turn clarification.

Most logging is one shot: "I slept 9 hours" needs no discussion. But
"I ate a burger" is worth a question, because the honest answer is
somewhere between 330 and 690 calories and guessing makes the whole
day's total meaningless.

So an agent may answer with a question instead of a result. It parks
what it knows so far as a Pending, the orchestrator routes the next
message straight back to that agent, and the exchange continues until
the agent has enough to log.

Only one clarification is ever open at a time. Two open questions is a
worse experience than one imprecise total.
"""
from dataclasses import dataclass, field
from datetime import datetime
import re


@dataclass
class Pending:
    """A question an agent is waiting on an answer to."""
    agent: str                      # who asked, and who gets the reply
    kind: str                       # what is being resolved, e.g. "food"
    question: str
    context: dict = field(default_factory=dict)
    turns: int = 0
    opened_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    # A clarification that has not resolved in a few turns is not going to.
    MAX_TURNS = 4

    def exhausted(self) -> bool:
        return self.turns >= self.MAX_TURNS


# Answers that close a question without adding anything.
NEGATIVE = (
    "no", "nope", "nah", "none", "nothing", "no thanks", "that is all",
    "thats all", "that's all", "nothing else", "just that", "only that",
    "that is it", "thats it", "that's it", "no more", "skip", "dont know",
    "don't know", "not sure", "no idea",
)

AFFIRMATIVE = ("yes", "yeah", "yep", "yup", "sure", "correct", "right", "ok")

# Closing phrases can arrive attached to a final item: "a coke, that's all".
CLOSING = ("nothing else", "that is all", "thats all", "that is it",
           "thats it", "just that", "only that", "no more", "nothing more",
           "that was all", "that was it", "im done", "i am done")

# Phrases that mean "forget the question I was answering".
CANCEL = ("cancel", "never mind", "nevermind", "forget it", "stop")


def _words(text: str) -> str:
    """Lowercase words only. Apostrophes are dropped, not spaced, so that
    "that's all" normalises to "thats all" and matches the list."""
    low = (text or "").lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z ]", " ", low).strip()


def is_negative(text: str) -> bool:
    low = _words(text)
    if not low:
        return False
    if low in NEGATIVE:
        return True
    # A closing phrase often arrives attached to a final item, as in
    # "a medium coke, that's all", so match it anywhere in the sentence.
    if any(phrase in low for phrase in CLOSING):
        return True
    # "no, that was it" - leading no counts, "no idea" already handled above.
    return bool(re.match(r"^(no|nope|nah|none|nothing)\b", low))


def strip_closing(text: str) -> str:
    """The message with its closing phrase removed, leaving any food named."""
    low = _words(text)
    for phrase in CLOSING:
        low = low.replace(phrase, " ")
    return re.sub(r"\s+", " ", low).strip(" ,.")


def is_affirmative(text: str) -> bool:
    low = _words(text)
    return low in AFFIRMATIVE or bool(re.match(r"^(yes|yeah|yep|yup)\b", low))


def is_cancel(text: str) -> bool:
    low = _words(text)
    return any(low.startswith(c) for c in CANCEL)
