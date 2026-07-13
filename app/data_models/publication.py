from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.data_models.request import (
    AtiDraft,
    TransportRequest,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_publication_id() -> str:
    return f"publication-{uuid4().hex}"


class PublicationApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    CONSUMED = "consumed"


class PublicationApproval(BaseModel):
    id: str = Field(
        default_factory=new_publication_id
    )

    request: TransportRequest
    draft: AtiDraft

    # Точное содержимое карточки и будущего
    # запроса ATI на момент создания approval.
    ati_preview: dict[str, Any] | None = None
    ati_preview_hash: str | None = None

    # Единый номер заявки в реестре Ярус Пик.
    registry_request_id: str | None = None

    source_chat_id: str
    source_message_id: str | None = None
    requested_by: str | None = None

    status: PublicationApprovalStatus = (
        PublicationApprovalStatus.PENDING
    )

    created_at: datetime = Field(
        default_factory=utcnow
    )
    processed_at: datetime | None = None
    processed_by: str | None = None

    publication_result: dict[str, Any] | None = None
