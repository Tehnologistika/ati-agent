from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.data_models.request_registry import (
    RegistryRequest,
)
from app.services.publication_repository import (
    PublicationApprovalRepository,
)
from app.services.request_registry import (
    RequestRegistryRepository,
)


_CLOSE_PREFIX = re.compile(
    r"^\s*(?:[#/]\s*)?ЗАКРЫТО\b",
    re.IGNORECASE,
)

_REQUEST_ID = re.compile(
    r"\bTL\s*[-–—]\s*A\s*[-–—]\s*"
    r"(\d{1,12})\b",
    re.IGNORECASE,
)

_LEGACY_NUMBER = re.compile(
    r"^\s*№\s*(\d{1,12})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CloseCommand:
    request_id: str | None
    reason: str | None


def _format_request_id(
    number: str,
) -> str:
    value = int(number)

    if value <= 0:
        raise ValueError(
            "Номер заявки должен быть больше нуля"
        )

    return f"TL-A-{value:06d}"


def is_close_command(
    text: str,
) -> bool:
    return bool(
        _CLOSE_PREFIX.match(
            str(text or "")
        )
    )


def parse_close_command(
    text: str,
) -> CloseCommand | None:
    raw = str(text or "")
    prefix = _CLOSE_PREFIX.match(raw)

    if prefix is None:
        return None

    remainder = raw[
        prefix.end():
    ].strip()

    request_id: str | None = None
    remove_span: tuple[int, int] | None = None

    request_match = _REQUEST_ID.search(
        remainder
    )

    if request_match:
        request_id = _format_request_id(
            request_match.group(1)
        )

        remove_span = request_match.span()

    else:
        legacy_match = _LEGACY_NUMBER.match(
            remainder
        )

        if legacy_match:
            request_id = _format_request_id(
                legacy_match.group(1)
            )

            remove_span = legacy_match.span()

    if remove_span is not None:
        start, end = remove_span

        remainder = (
            remainder[:start]
            + " "
            + remainder[end:]
        )

    reason = remainder.strip(
        " \t\r\n:;,.—–-"
    )

    return CloseCommand(
        request_id=request_id,
        reason=reason or None,
    )


def _resolve_target(
    command: CloseCommand,
    message: dict[str, Any],
    registry: RequestRegistryRepository,
) -> tuple[RegistryRequest, str]:
    if command.request_id:
        return (
            registry.get(
                command.request_id
            ),
            "request_id",
        )

    linked_message_id = str(
        message.get(
            "linked_message_id"
        )
        or ""
    ).strip()

    if not linked_message_id:
        raise ValueError(
            "Не указана заявка. Ответьте командой "
            "#ЗАКРЫТО на исходное сообщение "
            "с заявкой либо укажите номер "
            "TL-A-000001."
        )

    current_chat_id = str(
        message.get("chat_id")
        or ""
    ).strip()

    linked_chat_id = str(
        message.get("linked_chat_id")
        or current_chat_id
    ).strip()

    entry = registry.find_by_source(
        source_channel="max",
        source_chat_id=linked_chat_id,
        source_message_id=linked_message_id,
    )

    if (
        entry is None
        and linked_chat_id != current_chat_id
        and current_chat_id
    ):
        entry = registry.find_by_source(
            source_channel="max",
            source_chat_id=current_chat_id,
            source_message_id=(
                linked_message_id
            ),
        )

    if entry is None:
        raise KeyError(
            "Исходная заявка не найдена "
            "в реестре Ярус Пик"
        )

    return entry, "linked_message"


def process_max_close(
    *,
    database_url: str,
    owner_user_id: str,
    text: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    command = parse_close_command(text)

    if command is None:
        raise ValueError(
            "Сообщение не является "
            "командой закрытия"
        )

    registry = RequestRegistryRepository(
        database_url
    )

    approvals = (
        PublicationApprovalRepository(
            database_url
        )
    )

    try:
        entry, reference_type = _resolve_target(
            command,
            message,
            registry,
        )

        actor_id = str(
            message.get("user_id")
            or ""
        )

        closed, changed = registry.close(
            entry.request_id,
            actor_id=actor_id,
            owner_user_id=str(
                owner_user_id or ""
            ),
            reason=command.reason,
            actor_name=str(
                message.get("author_name")
                or ""
            )
            or None,
            close_message_id=str(
                message.get("message_id")
                or ""
            )
            or None,
        )

        cancelled_approvals = (
            approvals
            .cancel_pending_by_registry_request(
                closed.request_id,
                cancelled_by=actor_id,
                reason=(
                    command.reason
                    or "request_closed"
                ),
            )
        )

        if closed.ati_status == "closing":
            ati_action = (
                "close_publication_required"
            )
        elif cancelled_approvals:
            ati_action = "pending_cancelled"
        else:
            ati_action = "not_published"

        return {
            "registry_request": (
                closed.model_dump(
                    mode="json"
                )
            ),
            "closed_now": changed,
            "reference_type": reference_type,
            "cancelled_approval_ids": (
                cancelled_approvals
            ),
            "ati_action": ati_action,
        }

    finally:
        approvals.connection.close()
        registry.connection.close()
