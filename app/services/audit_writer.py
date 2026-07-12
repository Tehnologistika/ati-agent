from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


def _json_default(value: Any) -> Any:
    """Convert common application objects to stable JSON values."""

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, set):
        return sorted(value, key=str)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")

    raise TypeError(
        f"Object of type {value.__class__.__name__} is not JSON serializable"
    )


def write_event(
    event_type: str,
    details: dict[str, Any],
    path: str = "events.jsonl",
) -> None:
    """Append one structured event to a JSON Lines audit file."""

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "details": details,
    }

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    serialized = json.dumps(
        event,
        ensure_ascii=False,
        default=_json_default,
    )

    with target.open("a", encoding="utf-8") as file:
        file.write(serialized + "\n")
