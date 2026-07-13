from __future__ import annotations

import re
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


PROFILE_LABELS = {
    "single_vehicle": "Одно или штучное авто",
    "vehicle_list": "Список автомобилей",
    "full_carrier_lot": (
        "Лот — полный автовоз"
    ),
}


TECHNICAL_FIELD_LABELS = {
    "request_validation": (
        "Повторно проверить исходную заявку"
    ),
    "resolved_route_length": (
        "Проверить количество точек маршрута"
    ),
    "contact_ids": (
        "Подтвердить видимый контакт ATI"
    ),
    "board_ids": (
        "Подключить площадку публикации ATI"
    ),
    "body_type_ids": (
        "Получить ID кузова «автовоз» "
        "из справочника ATI"
    ),
    "currency_type_id": (
        "Получить ID валюты RUB "
        "из справочника ATI"
    ),
    "loading_date_type": (
        "Указать дату или режим готовности "
        "к загрузке"
    ),
    "first_date": (
        "Указать первую дату загрузки"
    ),
    "weight_confirmation": (
        "Подтвердить ориентировочный вес"
    ),
    "payment_type": (
        "Уточнить форму оплаты"
    ),
    "payment_delay_days": (
        "Указать срок отсрочки оплаты"
    ),
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
    *,
    ready_for_api: bool = True,
    dry_run: bool = False,
) -> list[list[dict[str, str]]]:
    """
    Build ATI publication buttons.

    In real mode the publish button is hidden until
    the complete ATI payload is ready.
    """

    row: list[dict[str, str]] = []

    if ready_for_api:
        row.append(
            {
                "type": "callback",
                "text": "Опубликовать",
                "payload": (
                    "publication:approve:"
                    f"{approval_id}"
                ),
            }
        )
    elif dry_run:
        row.append(
            {
                "type": "callback",
                "text": "Проверить DRY_RUN",
                "payload": (
                    "publication:approve:"
                    f"{approval_id}"
                ),
            }
        )

    row.append(
        {
            "type": "callback",
            "text": "Отклонить",
            "payload": (
                "publication:reject:"
                f"{approval_id}"
            ),
        }
    )

    return [row]


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
        opening = (
            f"{recipient}, в заявке "
            "не хватает данных:"
        )
    else:
        opening = (
            "В заявке не хватает данных:"
        )

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


def _missing_field_label(
    field: str,
    route_names: list[str],
) -> str:
    city_match = re.fullmatch(
        r"resolved_route\[(\d+)\]\.city_id",
        field,
    )

    if city_match:
        index = int(city_match.group(1))

        name = (
            route_names[index]
            if index < len(route_names)
            else f"точка №{index + 1}"
        )

        return (
            "Подтвердить населённый пункт "
            f"в справочнике ATI: {name}"
        )

    kind_match = re.fullmatch(
        r"resolved_route\[(\d+)\]\.kind",
        field,
    )

    if kind_match:
        index = int(kind_match.group(1))

        name = (
            route_names[index]
            if index < len(route_names)
            else f"точка №{index + 1}"
        )

        return (
            "Указать назначение промежуточной "
            f"точки: {name}"
        )

    return TECHNICAL_FIELD_LABELS.get(
        field,
        field,
    )


def _rate_text(
    request: dict[str, Any],
) -> str:
    rate = request.get("requested_rate")
    payment = str(
        request.get("payment_type") or ""
    ).strip()

    if rate is None:
        return "Запрос ставки"

    try:
        formatted = (
            f"{int(rate):,}"
            .replace(",", " ")
        )
    except (TypeError, ValueError):
        formatted = str(rate)

    if payment:
        return f"{formatted} ₽, {payment}"

    return f"{formatted} ₽"


def build_publication_card(
    request: dict[str, Any],
    draft: dict[str, Any],
    approval_id: str,
    ati_preview: dict[str, Any] | None = None,
) -> str:
    """
    Build the private owner card with the exact
    future ATI publication preview.
    """

    preview = ati_preview or {}

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
            "может выполнить реальную публикацию ATI."
        )
    )

    profile_value = preview.get("profile")

    if hasattr(profile_value, "value"):
        profile_value = profile_value.value

    profile = PROFILE_LABELS.get(
        str(profile_value or ""),
        (
            "Лот — полный автовоз"
            if bool(request.get("is_lot"))
            else "Обычная заявка"
        ),
    )

    ready_for_api = bool(
        preview.get("ready_for_api")
    )

    readiness = (
        "ГОТОВО К API"
        if ready_for_api
        else "ТРЕБУЕТ НАСТРОЙКИ"
    )

    route_names = [
        str(value).strip()
        for value in (
            request.get("route_points")
            or []
        )
        if str(value).strip()
    ]

    route = (
        " — ".join(route_names)
        if route_names
        else value(draft, "route")
    )

    application = (
        preview.get("payload", {})
        .get("cargo_application", {})
    )

    truck = application.get("truck", {})

    load_type = truck.get("load_type")

    load_type_label = {
        "ftl": "Полный автовоз (FTL)",
        "dont-care": (
            "Отдельная машина или догруз"
        ),
    }.get(
        str(load_type or ""),
        "не определено",
    )

    cargo_name = str(
        preview.get("cargo_name")
        or draft.get("cargo_description")
        or request.get("vehicle")
        or "не указано"
    ).strip()

    vehicle_count = preview.get(
        "estimated_vehicle_count"
    )

    weight = preview.get("weight_tons")
    estimated = bool(
        preview.get("weight_is_estimated")
    )

    if weight is None:
        weight_text = "не определён"
    else:
        weight_text = f"{weight:g} т"

        if estimated:
            weight_text += " — ориентировочно"

    note = str(
        preview.get("note") or ""
    ).strip()

    missing_fields = [
        str(field)
        for field in (
            preview.get("missing_fields")
            or []
        )
    ]

    warnings = [
        str(warning)
        for warning in (
            preview.get("warnings")
            or []
        )
    ]

    missing_text = "\n".join(
        "• "
        + _missing_field_label(
            field,
            route_names,
        )
        for field in missing_fields
    )

    warning_text = "\n".join(
        f"• {warning}"
        for warning in warnings
    )

    count_text = (
        "подбирается под вместимость автовоза"
        if (
            str(profile_value or "")
            == "full_carrier_lot"
            or bool(request.get("is_lot"))
        )
        else (
            str(vehicle_count)
            if vehicle_count is not None
            else "не определено"
        )
    )

    sections = [
        "## ЧЕРНОВИК ПУБЛИКАЦИИ В ATI",
        "",
        safety_text,
        "",
        f"**Готовность:** {readiness}",
        f"**Тип заявки:** {profile}",
        f"**Маршрут:** {route}",
        f"**Груз:** {cargo_name}",
        f"**Количество авто:** {count_text}",
        f"**Тип загрузки:** {load_type_label}",
        f"**Вес:** {weight_text}",
        f"**Ставка:** {_rate_text(request)}",
        (
            "**Дата готовности:** "
            f"{value(request, 'ready_date')}"
        ),
        (
            "**Состояние:** "
            f"{value(request, 'vehicle_condition')}"
        ),
        "",
        "### Текст объявления ATI",
        "",
        note or "Текст ещё не сформирован.",
    ]

    if missing_text:
        sections.extend(
            [
                "",
                "### Что осталось настроить",
                "",
                missing_text,
            ]
        )

    if warning_text:
        sections.extend(
            [
                "",
                "### Предупреждения",
                "",
                warning_text,
            ]
        )

    if not ready_for_api:
        sections.extend(
            [
                "",
                (
                    "**Реальная публикация "
                    "заблокирована до заполнения "
                    "всех обязательных полей.**"
                ),
            ]
        )

    sections.extend(
        [
            "",
            (
                "`Publication approval: "
                f"{approval_id}`"
            ),
            "",
            "Проверьте данные и выберите действие.",
        ]
    )

    text = "\n".join(sections)

    return text[:4000]
