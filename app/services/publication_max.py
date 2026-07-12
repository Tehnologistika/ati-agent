from __future__ import annotations

from typing import Any


FIELD_LABELS = {
    "origin": "город загрузки",
    "destination": "город выгрузки",
    "vehicle": "автомобиль или груз",
    "ready_date": "дата готовности",
    "vehicle_condition": "состояние автомобиля",
    "payment_type": "форма оплаты",
    "comment": "комментарий",
}


def is_publication_request(text: str) -> bool:
    """Return True for messages explicitly marked as #ЗАЯВКА."""

    normalized = str(text or "").upper()

    return "#ЗАЯВКА" in normalized


def parse_publication_callback(
    payload: str,
) -> tuple[str, str] | None:
    """
    Parse publication:approve:<id>
    or publication:reject:<id>.
    """

    parts = str(payload or "").split(":", 2)

    if len(parts) != 3:
        return None

    namespace, action, approval_id = parts

    if namespace != "publication":
        return None

    if action not in {"approve", "reject"}:
        return None

    if not approval_id.strip():
        return None

    return action, approval_id.strip()


def publication_buttons(
    approval_id: str,
) -> list[list[dict[str, str]]]:
    """Build buttons for one ATI publication approval."""

    return [
        [
            {
                "type": "callback",
                "text": "Опубликовать",
                "payload": (
                    "publication:approve:"
                    f"{approval_id}"
                ),
            },
            {
                "type": "callback",
                "text": "Отклонить",
                "payload": (
                    "publication:reject:"
                    f"{approval_id}"
                ),
            },
        ]
    ]


def build_missing_fields_message(
    missing_fields: list[str],
    *,
    author_name: str | None = None,
) -> str:
    """Build a clear request for missing application data."""

    labels = [
        FIELD_LABELS.get(field, field)
        for field in missing_fields
    ]

    recipient = str(author_name or "").strip()

    if recipient and recipient != "MAX user":
        opening = f"{recipient}, в заявке не хватает данных:"
    else:
        opening = "В заявке не хватает данных:"

    lines = "\n".join(
        f"• {label}"
        for label in labels
    )

    return (
        f"{opening}\n\n"
        f"{lines}\n\n"
        "Дополните заявку и отправьте её повторно "
        "с тегом `#ЗАЯВКА`."
    )


def build_publication_card(
    request: dict[str, Any],
    draft: dict[str, Any],
    approval_id: str,
) -> str:
    """Build the private owner card for ATI publication."""

    def value(
        source: dict[str, Any],
        key: str,
    ) -> str:
        result = source.get(key)

        if result is None:
            return "не указано"

        cleaned = str(result).strip()

        return cleaned or "не указано"

    dry_run = bool(draft.get("dry_run"))

    safety_text = (
        "**Безопасный режим:** включён `DRY_RUN`. "
        "Реальная публикация в ATI не выполняется."
        if dry_run
        else (
            "**Внимание:** после подтверждения система "
            "сможет выполнить публикацию в ATI."
        )
    )

    text = (
        "## ЧЕРНОВИК ПУБЛИКАЦИИ В ATI\n\n"
        f"{safety_text}\n\n"
        f"**Маршрут:** "
        f"{value(request, 'origin')} — "
        f"{value(request, 'destination')}\n"
        f"**Автомобиль:** "
        f"{value(request, 'vehicle')}\n"
        f"**Дата готовности:** "
        f"{value(request, 'ready_date')}\n"
        f"**Состояние:** "
        f"{value(request, 'vehicle_condition')}\n"
        f"**Оплата:** "
        f"{value(request, 'payment_type')}\n"
        f"**Комментарий:** "
        f"{value(request, 'comment')}\n\n"
        "### Черновик ATI\n\n"
        f"**Заголовок:** "
        f"{value(draft, 'title')}\n"
        f"**Маршрут:** "
        f"{value(draft, 'route')}\n"
        f"**Описание груза:** "
        f"{value(draft, 'cargo_description')}\n"
        f"**Дата:** "
        f"{value(draft, 'ready_date')}\n"
        f"**Оплата:** "
        f"{value(draft, 'payment_type')}\n"
        f"**Комментарий:** "
        f"{value(draft, 'comment')}\n\n"
        f"`Publication approval: {approval_id}`\n\n"
        "Проверьте данные и выберите действие."
    )

    return text[:4000]
