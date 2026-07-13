from __future__ import annotations

import hmac
from typing import Any

from app.data_models.request_registry import (
    RegistryRequest,
)


CLOSED_CLIENT_MESSAGE = (
    "Эта заявка уже закрыта и больше не актуальна. "
    "Для новой перевозки необходимо оформить "
    "отдельную актуальную заявку."
)


def registry_api_secret_is_valid(
    provided_secret: str | None,
    configured_secret: str | None,
) -> bool:
    """
    Проверить секрет в постоянное время.

    При отсутствии настроенного секрета API
    считается выключенным.
    """

    provided = str(
        provided_secret or ""
    ).strip()

    configured = str(
        configured_secret or ""
    ).strip()

    if not provided or not configured:
        return False

    return hmac.compare_digest(
        provided.encode("utf-8"),
        configured.encode("utf-8"),
    )


def build_registry_status(
    entry: RegistryRequest,
) -> dict[str, Any]:
    """
    Минимальный read-only ответ для Аюба.

    Полный текст заявки и внутренние данные
    клиента через этот маршрут не раскрываются.
    """

    may_continue = bool(entry.is_active)

    return {
        "ok": True,
        "request_id": entry.request_id,
        "status": entry.status.value,
        "is_active": entry.is_active,
        "version": entry.version,
        "ayub_status": entry.ayub_status,
        "ati_status": entry.ati_status,
        "created_at": (
            entry.created_at.isoformat()
        ),
        "updated_at": (
            entry.updated_at.isoformat()
        ),
        "closed_at": (
            entry.closed_at.isoformat()
            if entry.closed_at
            else None
        ),
        "closed_by": entry.closed_by,
        "closed_by_name": (
            entry.closed_by_name
        ),
        "close_reason": entry.close_reason,
        "reply_policy": {
            "may_continue": may_continue,
            "client_message": (
                None
                if may_continue
                else CLOSED_CLIENT_MESSAGE
            ),
        },
    }
