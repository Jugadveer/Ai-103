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


def chat(system: str, user: str, temperature: float = 0.3) -> str:
    """Single-turn completion. Falls back to the raw prompt in mock mode."""
    if not available():
        return ""

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
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        log.error("llm_failed", error=str(exc)[:160])
        return ""
