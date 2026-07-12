import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_event(event_type: str, details: dict[str, Any], path: str = "events.jsonl") -> None:
    """Append a local JSONL event for traceability in MVP mode."""

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "details": details,
    }

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
