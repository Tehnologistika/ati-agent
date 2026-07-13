from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.data_models.request import (
    TransportRequest,
)
from app.data_models.request_registry import (
    RegistryEvent,
    RegistryRequest,
    RegistryRequestStatus,
    utcnow,
)


def _db_path(database_url: str) -> str:
    prefix = "sqlite:///"

    if not database_url.startswith(prefix):
        raise ValueError(
            "Request registry currently supports "
            "only sqlite:/// database URLs"
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


def _clean_optional(
    value: str | None,
) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _source_key(
    source_channel: str,
    source_chat_id: str,
    source_message_id: str | None,
) -> str | None:
    """
    Один источник + один чат + одно сообщение
    должны создавать только одну заявку.
    """

    channel = str(
        source_channel or ""
    ).strip().casefold()

    chat_id = str(
        source_chat_id or ""
    ).strip()

    message_id = str(
        source_message_id or ""
    ).strip()

    if not channel or not chat_id or not message_id:
        return None

    raw = "\x00".join(
        [
            channel,
            chat_id,
            message_id,
        ]
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


class RequestRegistryRepository:
    """
    Единый регистратор заявок «Ярус Пик».

    Запись создаётся здесь один раз, а остальные
    агенты работают с её request_id и статусом.
    """

    def __init__(self, database_url: str):
        self.path = _db_path(database_url)

        self.connection = sqlite3.connect(
            self.path,
            timeout=10,
        )

        self.connection.row_factory = sqlite3.Row

        self.connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        self.connection.execute(
            "PRAGMA busy_timeout = 5000"
        )

        if self.path != ":memory:":
            self.connection.execute(
                "PRAGMA journal_mode = WAL"
            )

        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS
            request_registry (
                sequence_id INTEGER
                    PRIMARY KEY AUTOINCREMENT,

                request_id TEXT UNIQUE,
                payload TEXT NOT NULL,

                status TEXT NOT NULL,
                is_active INTEGER NOT NULL,

                source_key TEXT,
                source_channel TEXT NOT NULL,
                source_chat_id TEXT NOT NULL,
                source_message_id TEXT,

                author_user_id TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                closed_at TEXT,
                closed_by TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_request_registry_source_key
            ON request_registry(source_key)
            WHERE source_key IS NOT NULL;

            CREATE TABLE IF NOT EXISTS
            request_registry_events (
                event_id INTEGER
                    PRIMARY KEY AUTOINCREMENT,

                request_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT,

                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
            idx_request_registry_events_request
            ON request_registry_events(
                request_id,
                event_id
            );
            """
        )

        self.connection.commit()

    def _entry_from_row(
        self,
        row: sqlite3.Row,
    ) -> RegistryRequest:
        return RegistryRequest.model_validate_json(
            row["payload"]
        )

    def _insert_event(
        self,
        *,
        request_id: str,
        event_type: str,
        actor_id: str | None,
        details: dict[str, Any] | None = None,
        created_at=None,
    ) -> None:
        timestamp = created_at or utcnow()

        self.connection.execute(
            """
            INSERT INTO request_registry_events (
                request_id,
                event_type,
                actor_id,
                details,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                request_id,
                event_type,
                _clean_optional(actor_id),
                json.dumps(
                    details or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                timestamp.isoformat(),
            ),
        )

    def find_by_source(
        self,
        *,
        source_channel: str,
        source_chat_id: str,
        source_message_id: str | None,
    ) -> RegistryRequest | None:
        source_key = _source_key(
            source_channel,
            source_chat_id,
            source_message_id,
        )

        if source_key is None:
            return None

        row = self.connection.execute(
            """
            SELECT payload
            FROM request_registry
            WHERE source_key = ?
            """,
            (source_key,),
        ).fetchone()

        if row is None:
            return None

        return self._entry_from_row(row)

    def create_or_get(
        self,
        *,
        request: TransportRequest,
        source_channel: str,
        source_chat_id: str,
        source_message_id: str | None,
        author_user_id: str | None,
    ) -> tuple[RegistryRequest, bool]:
        """
        Возвращает (заявка, создана_сейчас).
        """

        channel = (
            str(source_channel or "").strip()
            or "unknown"
        )

        chat_id = str(
            source_chat_id or ""
        ).strip()

        message_id = _clean_optional(
            source_message_id
        )

        author_id = _clean_optional(
            author_user_id
        )

        source_key = _source_key(
            channel,
            chat_id,
            message_id,
        )

        try:
            self.connection.execute(
                "BEGIN IMMEDIATE"
            )

            if source_key is not None:
                row = self.connection.execute(
                    """
                    SELECT payload
                    FROM request_registry
                    WHERE source_key = ?
                    """,
                    (source_key,),
                ).fetchone()

                if row is not None:
                    self.connection.commit()

                    return (
                        self._entry_from_row(row),
                        False,
                    )

            now = utcnow()

            cursor = self.connection.execute(
                """
                INSERT INTO request_registry (
                    request_id,
                    payload,
                    status,
                    is_active,
                    source_key,
                    source_channel,
                    source_chat_id,
                    source_message_id,
                    author_user_id,
                    created_at,
                    updated_at,
                    closed_at,
                    closed_by
                )
                VALUES (
                    NULL,
                    '{}',
                    ?,
                    1,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    NULL,
                    NULL
                )
                """,
                (
                    RegistryRequestStatus
                    .FORMED.value,
                    source_key,
                    channel,
                    chat_id,
                    message_id,
                    author_id,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

            sequence_id = int(
                cursor.lastrowid
            )

            request_id = (
                f"TL-A-{sequence_id:06d}"
            )

            entry = RegistryRequest(
                request_id=request_id,
                request=request,
                source_channel=channel,
                source_chat_id=chat_id,
                source_message_id=message_id,
                author_user_id=author_id,
                created_at=now,
                updated_at=now,
            )

            self.connection.execute(
                """
                UPDATE request_registry
                SET
                    request_id = ?,
                    payload = ?
                WHERE sequence_id = ?
                """,
                (
                    request_id,
                    entry.model_dump_json(),
                    sequence_id,
                ),
            )

            self._insert_event(
                request_id=request_id,
                event_type="request.created",
                actor_id=author_id,
                details={
                    "source_channel": channel,
                    "source_chat_id": chat_id,
                    "source_message_id": (
                        message_id
                    ),
                },
                created_at=now,
            )

            self.connection.commit()

            return entry, True

        except Exception:
            self.connection.rollback()
            raise

    def get(
        self,
        request_id: str,
    ) -> RegistryRequest:
        normalized = str(
            request_id or ""
        ).strip().upper()

        row = self.connection.execute(
            """
            SELECT payload
            FROM request_registry
            WHERE request_id = ?
            """,
            (normalized,),
        ).fetchone()

        if row is None:
            raise KeyError(
                "Registry request not found: "
                f"{normalized}"
            )

        return self._entry_from_row(row)

    def close(
        self,
        request_id: str,
        *,
        actor_id: str,
        owner_user_id: str,
        reason: str | None = None,
        actor_name: str | None = None,
        close_message_id: str | None = None,
    ) -> tuple[RegistryRequest, bool]:
        """
        Закрыть заявку вправе только:
        1. Навигатор-автор;
        2. владелец системы.

        Возвращает (заявка, закрыта_сейчас).
        """

        normalized_id = str(
            request_id or ""
        ).strip().upper()

        actor = str(
            actor_id or ""
        ).strip()

        owner = str(
            owner_user_id or ""
        ).strip()

        actor_display_name = _clean_optional(
            actor_name
        )

        closing_message_id = _clean_optional(
            close_message_id
        )

        if not actor:
            raise PermissionError(
                "Не удалось определить пользователя"
            )

        try:
            self.connection.execute(
                "BEGIN IMMEDIATE"
            )

            row = self.connection.execute(
                """
                SELECT payload
                FROM request_registry
                WHERE request_id = ?
                """,
                (normalized_id,),
            ).fetchone()

            if row is None:
                raise KeyError(
                    "Registry request not found: "
                    f"{normalized_id}"
                )

            entry = self._entry_from_row(row)

            is_owner = (
                bool(owner)
                and actor == owner
            )

            is_author = (
                bool(entry.author_user_id)
                and actor
                == str(entry.author_user_id)
            )

            if not is_owner and not is_author:
                raise PermissionError(
                    "Закрыть заявку может только "
                    "Навигатор, который её опубликовал, "
                    "либо владелец"
                )

            if (
                not entry.is_active
                or entry.status
                == RegistryRequestStatus.CLOSED
            ):
                self.connection.commit()
                return entry, False

            now = utcnow()

            entry.status = (
                RegistryRequestStatus.CLOSED
            )

            entry.is_active = False
            entry.ayub_status = "inactive"

            if entry.ati_status in {
                "published",
                "active",
            }:
                entry.ati_status = "closing"

            entry.closed_at = now
            entry.closed_by = actor
            entry.closed_by_name = (
                actor_display_name
            )
            entry.close_message_id = (
                closing_message_id
            )
            entry.close_reason = (
                _clean_optional(reason)
            )

            entry.updated_at = now
            entry.version += 1

            self.connection.execute(
                """
                UPDATE request_registry
                SET
                    payload = ?,
                    status = ?,
                    is_active = 0,
                    updated_at = ?,
                    closed_at = ?,
                    closed_by = ?
                WHERE request_id = ?
                """,
                (
                    entry.model_dump_json(),
                    entry.status.value,
                    now.isoformat(),
                    now.isoformat(),
                    actor,
                    normalized_id,
                ),
            )

            self._insert_event(
                request_id=normalized_id,
                event_type="request.closed",
                actor_id=actor,
                details={
                    "reason": entry.close_reason,
                    "closed_by_owner": is_owner,
                    "closed_by_author": is_author,
                    "closed_by_name": (
                        entry.closed_by_name
                    ),
                    "close_message_id": (
                        entry.close_message_id
                    ),
                    "ati_status": entry.ati_status,
                    "ayub_status": entry.ayub_status,
                },
                created_at=now,
            )

            self.connection.commit()

            return entry, True

        except Exception:
            self.connection.rollback()
            raise

    def list_events(
        self,
        request_id: str,
    ) -> list[RegistryEvent]:
        rows = self.connection.execute(
            """
            SELECT
                event_id,
                request_id,
                event_type,
                actor_id,
                details,
                created_at
            FROM request_registry_events
            WHERE request_id = ?
            ORDER BY event_id
            """,
            (
                str(request_id or "")
                .strip()
                .upper(),
            ),
        ).fetchall()

        return [
            RegistryEvent(
                event_id=int(row["event_id"]),
                request_id=str(
                    row["request_id"]
                ),
                event_type=str(
                    row["event_type"]
                ),
                actor_id=(
                    str(row["actor_id"])
                    if row["actor_id"]
                    is not None
                    else None
                ),
                details=json.loads(
                    row["details"]
                ),
                created_at=row["created_at"],
            )
            for row in rows
        ]
