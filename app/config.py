"""Loads settings from .env. One place for all configuration."""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# Run with canned responses when Azure keys are not set up yet.
MOCK_MODE = _get("MOCK_MODE", "true").lower() == "true"

# Azure OpenAI
AZURE_OPENAI_ENDPOINT = _get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = _get("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT = _get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
AZURE_OPENAI_API_VERSION = _get("AZURE_OPENAI_API_VERSION", "2024-10-21")

# Azure AI Search (RAG)
AZURE_SEARCH_ENDPOINT = _get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_API_KEY = _get("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_INDEX = _get("AZURE_SEARCH_INDEX", "health-kb")

# Azure AI Speech
AZURE_SPEECH_KEY = _get("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = _get("AZURE_SPEECH_REGION", "centralindia")
AZURE_SPEECH_VOICE = _get("AZURE_SPEECH_VOICE", "en-IN-NeerjaNeural")

# Azure AI Content Safety
AZURE_CONTENT_SAFETY_ENDPOINT = _get("AZURE_CONTENT_SAFETY_ENDPOINT")
AZURE_CONTENT_SAFETY_KEY = _get("AZURE_CONTENT_SAFETY_KEY")

# Populate a fresh deployment with the demo month, so a tester never
# lands on an empty app. Only ever runs when nothing has been logged, so
# it cannot overwrite real data on a host with a persistent disk.
SEED_ON_EMPTY = _get("SEED_ON_EMPTY", "false").lower() == "true"


# --- storage -------------------------------------------------------------
# Serverless hosts give a read-only filesystem with one writable temp
# directory, and the container is thrown away between requests. So the
# path is resolved at startup rather than assumed, and the app reports
# honestly whether anything it saves will still be there later.

def _resolve_storage(preferred: str) -> tuple[str, bool]:
    """Return (path, persistent). Falls back to temp on a read-only disk."""
    import os
    import tempfile

    candidate = os.path.abspath(preferred)
    folder = os.path.dirname(candidate) or "."
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".write-probe")
        with open(probe, "w") as handle:
            handle.write("ok")
        os.remove(probe)
        return candidate, True
    except OSError:
        fallback = os.path.join(tempfile.gettempdir(), "health_coach.db")
        return fallback, False


DB_PATH, STORAGE_PERSISTENT = _resolve_storage(
    _get("DB_PATH", "health_coach.db"))

# Shown in the UI and spoken in the first reply. Not medical advice.
DISCLAIMER = (
    "I'm a wellness coach, not a doctor. I share general information only "
    "and never diagnose. For anything medical, please see a qualified clinician."
)
