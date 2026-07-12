from __future__ import annotations

import sqlite3
from pathlib import Path

from app.data_models.publication import (
    PublicationApproval,
    PublicationApprovalStatus,
)


def _db_path(database_url: str) -> str:
    prefix = "sqlite:///"

    if not database_url.startswith(prefix):
        raise ValueError(
            "Publication repository supports only "
            "sqlite:/// database URLs"
        )

    value = database_url[len(prefix):]

    if value == ":memory:":
        return value

    path = Path(value)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return str(path)


class PublicationApprovalRepository:
    """Persistent one-time ATI publication approvals."""

    def __init__(self, database_url: str):
        self.path = _db_path(database_url)
        self.connection = sqlite3.connect(
            self.path
        )
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS
            publication_approvals (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                processed_at TEXT,
                processed_by TEXT
            );
            """
        )
        self.connection.commit()

    def save(
        self,
        approval: PublicationApproval,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO publication_approvals (
                id,
                payload,
                status,
                created_at,
                processed_at,
                processed_by
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload = excluded.payload,
                status = excluded.status,
                processed_at = excluded.processed_at,
                processed_by = excluded.processed_by
            """,
            (
                approval.id,
                approval.model_dump_json(),
                approval.status.value,
                approval.created_at.isoformat(),
                (
                    approval.processed_at.isoformat()
                    if approval.processed_at
                    else None
                ),
                approval.processed_by,
            ),
        )
        self.connection.commit()

    def create(
        self,
        approval: PublicationApproval,
    ) -> PublicationApproval:
        self.save(approval)
        return approval

    def get(
        self,
        approval_id: str,
    ) -> PublicationApproval:
        row = self.connection.execute(
            """
            SELECT payload
            FROM publication_approvals
            WHERE id = ?
            """,
            (approval_id,),
        ).fetchone()

        if row is None:
            raise KeyError(
                "Publication approval not found: "
                f"{approval_id}"
            )

        return PublicationApproval.model_validate_json(
            row["payload"]
        )

    def approve(
        self,
        approval_id: str,
        approved_by: str,
    ) -> PublicationApproval:
        approval = self.get(approval_id)

        if (
            approval.status
            != PublicationApprovalStatus.PENDING
        ):
            raise ValueError(
                "Publication approval is not pending: "
                f"{approval.status.value}"
            )

        from app.data_models.publication import (
            utcnow,
        )

        approval.status = (
            PublicationApprovalStatus.APPROVED
        )
        approval.processed_at = utcnow()
        approval.processed_by = approved_by

        self.save(approval)
        return approval

    def reject(
        self,
        approval_id: str,
        rejected_by: str,
    ) -> PublicationApproval:
        approval = self.get(approval_id)

        if (
            approval.status
            != PublicationApprovalStatus.PENDING
        ):
            raise ValueError(
                "Publication approval is not pending: "
                f"{approval.status.value}"
            )

        from app.data_models.publication import (
            utcnow,
        )

        approval.status = (
            PublicationApprovalStatus.REJECTED
        )
        approval.processed_at = utcnow()
        approval.processed_by = rejected_by

        self.save(approval)
        return approval

    def consume(
        self,
        approval_id: str,
        publication_result: dict,
    ) -> PublicationApproval:
        approval = self.get(approval_id)

        if (
            approval.status
            != PublicationApprovalStatus.APPROVED
        ):
            raise ValueError(
                "Publication approval cannot be consumed: "
                f"{approval.status.value}"
            )

        approval.status = (
            PublicationApprovalStatus.CONSUMED
        )
        approval.publication_result = (
            publication_result
        )

        self.save(approval)
        return approval
