from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.data_models.request import (
    TransportRequest,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RegistryRequestStatus(str, Enum):
    FORMED = "formed"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class RegistryRequest(BaseModel):
    """
    Единая карточка заявки Ярус Пик.

    Эту запись в дальнейшем будут читать Аюб,
    ATI-агент и Google Sheets.
    """

    request_id: str = Field(
        pattern=r"^TL-A-\d{6,}$",
    )

    request: TransportRequest

    source_channel: str = Field(
        min_length=1,
    )

    source_chat_id: str
    source_message_id: str | None = None

    # MAX ID Навигатора, опубликовавшего заявку.
    author_user_id: str | None = None

    status: RegistryRequestStatus = (
        RegistryRequestStatus.FORMED
    )

    is_active: bool = True

    # Отдельные технические статусы агентов.
    ati_status: str = "not_published"
    ayub_status: str = "active"

    created_at: datetime = Field(
        default_factory=utcnow
    )

    updated_at: datetime = Field(
        default_factory=utcnow
    )

    closed_at: datetime | None = None
    closed_by: str | None = None
    closed_by_name: str | None = None
    close_message_id: str | None = None
    close_reason: str | None = None

    version: int = Field(
        default=1,
        ge=1,
    )


class RegistryEvent(BaseModel):
    event_id: int

    request_id: str
    event_type: str

    actor_id: str | None = None
    details: dict[str, Any] = Field(
        default_factory=dict
    )

    created_at: datetime
