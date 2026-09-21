"""Azure OpenAI wrapper. Returns canned text in MOCK_MODE."""
from app import config
from app.core import logging as log
from app.core.retry import with_retry

_client = None

# Cost control: every call is capped. gpt-4o-mini at this size costs
# fractions of a cent, so a full demo run stays well inside the student credit.
MAX_TOKENS = 400


def _get_client():
    global _client
    if _client is None:
        from openai import AzureOpenAI
        _client = AzureOpenAI(
            azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
            api_key=config.AZURE_OPENAI_API_KEY,
            api_version=config.AZURE_OPENAI_API_VERSION,
        )
    return _client


def available() -> bool:
    return not config.MOCK_MODE and bool(
        config.AZURE_OPENAI_ENDPOINT and config.AZURE_OPENAI_API_KEY
    )


def chat_with_reason(system: str, user: str,
                     temperature: float = 0.3) -> tuple[str, str]:
    """
    Single-turn completion, and why it is empty when it is.

    Reasons: ok, not_configured, content_filter, error.

    The distinction matters to the safety layer. Azure OpenAI runs its
    own content filter, and a prompt it refuses raises rather than
    returning text. Swallowing that into "" made it look exactly like the
    network being down, so asking "how many mg of paracetamol should I
    take" produced an empty triage result, fell through to Content
    Safety, was classified as self-harm and answered with a crisis
    helpline. Azure declining to process a message is information: it
    means the message was sensitive, not that the service was missing.
    """
    if not available():
        return "", "not_configured"

    def _call():
        return _get_client().chat.completions.create(
            model=config.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=MAX_TOKENS,
        )

    try:
        resp = with_retry(_call, label="azure_openai")
        return (resp.choices[0].message.content or "").strip(), "ok"
    except Exception as exc:
        detail = str(exc)
        filtered = ("content_filter" in detail
                    or "content management policy" in detail.lower()
                    or getattr(getattr(exc, "body", None), "get", lambda k: None)("code")
                    == "content_filter")
        log.error("llm_failed", error=detail[:160],
                  filtered=bool(filtered))
        return "", ("content_filter" if filtered else "error")


def chat(system: str, user: str, temperature: float = 0.3) -> str:
    """Single-turn completion. Empty when it could not answer."""
    return chat_with_reason(system, user, temperature)[0]


VISION_PROMPT = (
    "Identify food in this image. Rules, in order of importance. "
    "1. If you are not confident the image clearly shows food, reply "
    "exactly: none. "
    "2. A blank image, a solid colour, a screenshot, a person or an object "
    "is NOT food. Reply: none. "
    "3. Never invent items that are not plainly visible. "
    "4. Otherwise list only what you plainly see, comma separated with "
    "quantities, for example: 1 cheeseburger, 1 medium fries. "
    "Reply with the list or the single word none, nothing else."
)


def describe_food_photo(data_url: str) -> str:
    """
    Ask Azure OpenAI to name the food in a photo.

    Returns '' when vision is unavailable or nothing edible is visible, so
    the caller falls back to asking the user what they ate.
    """
    if not available():
        return ""

    def _call():
        return _get_client().chat.completions.create(
            model=config.AZURE_OPENAI_DEPLOYMENT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            temperature=0,
            max_tokens=120,
        )

    try:
        resp = with_retry(_call, label="azure_vision")
        text = (resp.choices[0].message.content or "").strip()
        if text.lower().startswith("none"):
            return ""
        log.info("photo_described", text=text[:80])
        return text
    except Exception as exc:
        log.error("vision_failed", error=str(exc)[:160])
        return ""
