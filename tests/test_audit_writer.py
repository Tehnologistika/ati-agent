import json
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from app.services.audit_writer import write_event


class ExampleStatus(Enum):
    ACTIVE = "active"


def test_audit_writer_serializes_application_types(tmp_path):
    target = tmp_path / "events.jsonl"
    event_time = datetime(2026, 7, 12, 14, 0, tzinfo=timezone.utc)
    event_id = uuid4()

    write_event(
        "test_event",
        {
            "created_at": event_time,
            "event_id": event_id,
            "status": ExampleStatus.ACTIVE,
        },
        path=str(target),
    )

    rows = target.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1

    data = json.loads(rows[0])
    assert data["event_type"] == "test_event"
    assert data["details"]["created_at"] == event_time.isoformat()
    assert data["details"]["event_id"] == str(event_id)
    assert data["details"]["status"] == "active"
