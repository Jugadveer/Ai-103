"""
Minimal structured logging. Writes one line per event to stderr.

Deliberately not the `logging` module - a few functions are easier to
explain in a viva and cost nothing at runtime.
"""
import json
import sys
from datetime import datetime

# Set to False to silence output during tests.
ENABLED = True


def _emit(level: str, event: str, **fields) -> None:
    if not ENABLED:
        return
    record = {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "event": event,
    }
    record.update(fields)
    print(json.dumps(record, default=str), file=sys.stderr)


def info(event: str, **fields) -> None:
    _emit("INFO", event, **fields)


def warn(event: str, **fields) -> None:
    _emit("WARN", event, **fields)


def error(event: str, **fields) -> None:
    _emit("ERROR", event, **fields)
