"""
RAG lookup. Uses Azure AI Search when configured, otherwise the local
JSON knowledge base in data/health_kb/ so the app still runs offline.
"""
import json
import pathlib
from app import config
from app.core import logging as log
from app.core.retry import with_retry

_KB_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "health_kb" / "kb.json"
_local_kb: list[dict] | None = None


def _load_local() -> list[dict]:
    global _local_kb
    if _local_kb is None:
        if _KB_PATH.exists():
            _local_kb = json.loads(_KB_PATH.read_text(encoding="utf-8"))
        else:
            _local_kb = []
    return _local_kb


def _local_search(query: str, top: int) -> list[dict]:
    """Plain keyword overlap - good enough as a fallback."""
    words = {w for w in query.lower().split() if len(w) > 3}
    scored = []
    for doc in _load_local():
        haystack = (doc.get("title", "") + " " + doc.get("content", "")).lower()
        score = sum(1 for w in words if w in haystack)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda p: p[0], reverse=True)
    return [doc for _, doc in scored[:top]]


def lookup(query: str, top: int = 2) -> list[dict]:
    """Return the most relevant knowledge-base passages for a query."""
    if config.MOCK_MODE or not config.AZURE_SEARCH_ENDPOINT:
        return _local_search(query, top)

    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=config.AZURE_SEARCH_ENDPOINT,
            index_name=config.AZURE_SEARCH_INDEX,
            credential=AzureKeyCredential(config.AZURE_SEARCH_API_KEY),
        )
        results = with_retry(
            lambda: list(client.search(search_text=query, top=top)),
            label="azure_search")
        return [
            {
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "source": r.get("source", "Azure AI Search"),
            }
            for r in results
        ]
    except Exception as exc:  # fall back rather than crash the demo
        log.warn("search_unavailable", error=str(exc)[:120])
        return _local_search(query, top)
