import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.data_models.negotiation import (
    ApprovalRequest,
    ApprovalStatus,
    NegotiationSession,
)


def _db_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("NegotiationRepository currently supports only sqlite:/// URLs")
    value = database_url[len(prefix):]
    if value == ":memory:":
        return value
    path = Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


class NegotiationRepository:
    """SQLite persistence for complete negotiation sessions and one-time approvals."""

    def __init__(self, database_url: str):
        self.path = _db_path(database_url)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS negotiations (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                negotiation_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                approved_at TEXT,
                approved_by TEXT
            );
            """
        )
        self.connection.commit()

    def save_session(self, session: NegotiationSession) -> None:
        session.updated_at = datetime.now(timezone.utc)
        self.connection.execute(
            """
            INSERT INTO negotiations(id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
            """,
            (session.id, session.model_dump_json(), session.updated_at.isoformat()),
        )
        self.connection.commit()

    def get_session(self, negotiation_id: str) -> NegotiationSession:
        row = self.connection.execute(
            "SELECT payload FROM negotiations WHERE id = ?", (negotiation_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Negotiation not found: {negotiation_id}")
        return NegotiationSession.model_validate_json(row["payload"])

    def create_approval(self, negotiation_id: str, message_id: str) -> ApprovalRequest:
        approval = ApprovalRequest(negotiation_id=negotiation_id, message_id=message_id)
        self.connection.execute(
            """
            INSERT INTO approvals(id, negotiation_id, message_id, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                approval.id,
                approval.negotiation_id,
                approval.message_id,
                approval.status.value,
                approval.created_at.isoformat(),
            ),
        )
        self.connection.commit()
        return approval

    def get_approval(self, approval_id: str) -> ApprovalRequest:
        row = self.connection.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Approval not found: {approval_id}")
        return ApprovalRequest(
            id=row["id"],
            negotiation_id=row["negotiation_id"],
            message_id=row["message_id"],
            status=ApprovalStatus(row["status"]),
            created_at=row["created_at"],
            approved_at=row["approved_at"],
            approved_by=row["approved_by"],
        )

    def approve(self, approval_id: str, approved_by: str) -> ApprovalRequest:
        approval = self.get_approval(approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval is not pending: {approval.status.value}")
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            UPDATE approvals SET status = ?, approved_at = ?, approved_by = ? WHERE id = ?
            """,
            (ApprovalStatus.APPROVED.value, now, approved_by, approval_id),
        )
        self.connection.commit()
        return self.get_approval(approval_id)

    def reject(self, approval_id: str, rejected_by: str) -> ApprovalRequest:
        approval = self.get_approval(approval_id)

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Approval is not pending: {approval.status.value}"
            )

        now = datetime.now(timezone.utc).isoformat()

        self.connection.execute(
            """
            UPDATE approvals
            SET status = ?, approved_at = ?, approved_by = ?
            WHERE id = ?
            """,
            (
                ApprovalStatus.REJECTED.value,
                now,
                rejected_by,
                approval_id,
            ),
        )
        self.connection.commit()

        return self.get_approval(approval_id)

    def consume(self, approval_id: str, message_id: str) -> ApprovalRequest:
        approval = self.get_approval(approval_id)
        if approval.message_id != message_id:
            raise ValueError("Approval belongs to a different message")
        if approval.status != ApprovalStatus.APPROVED:
            raise ValueError(f"Approval cannot be consumed: {approval.status.value}")
        self.connection.execute(
            "UPDATE approvals SET status = ? WHERE id = ?",
            (ApprovalStatus.CONSUMED.value, approval_id),
        )
        self.connection.commit()
        return self.get_approval(approval_id)
