from __future__ import annotations

from datetime import date
from typing import Any

from app.data_models.ati_publication import (
    LoadingDateType,
)


MONTH_NAMES = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_ru_date(value: date) -> str:
    return (
        f"{value.day} "
        f"{MONTH_NAMES[value.month]} "
        f"{value.year}"
    )


def format_ru_period(
    first: date,
    last: date | None,
) -> str:
    if last is None or last == first:
        return format_ru_date(first)

    if (
        first.year == last.year
        and first.month == last.month
    ):
        return (
            f"{first.day}–{last.day} "
            f"{MONTH_NAMES[first.month]} "
            f"{first.year}"
        )

    return (
        f"{format_ru_date(first)} — "
        f"{format_ru_date(last)}"
    )


def format_loading_schedule_note(
    date_type: LoadingDateType | None,
    first_date: date | None,
    last_date: date | None,
) -> str | None:
    """Return grammatically neutral Russian text."""

    if date_type is None:
        return None

    if date_type == LoadingDateType.READY:
        return "Готово к отправке."

    if date_type == LoadingDateType.PERMANENT:
        return "Загрузка выполняется постоянно."

    if date_type == LoadingDateType.RATE_REQUEST:
        return (
            "Дата готовности уточняется; "
            "заявка используется для запроса ставки."
        )

    if first_date is None:
        return None

    period = format_ru_period(
        first_date,
        last_date,
    )

    if last_date and last_date != first_date:
        return (
            "Период готовности к отправке: "
            f"{period} г."
        )

    return (
        "Готовность к отправке: "
        f"{period} г."
    )


def format_loading_dates_payload(
    value: dict[str, Any] | None,
) -> str:
    """Format the dates section from the future ATI JSON."""

    data = value or {}
    date_type = str(
        data.get("type") or ""
    )

    if date_type == "ready":
        return "Готово к отправке"

    if date_type == "permanent":
        return "Постоянная загрузка"

    if date_type == "rate-request":
        return (
            "Запрос ставки; "
            "дата готовности уточняется"
        )

    if date_type != "from-date":
        return "не указано"

    first_raw = data.get("first_date")
    last_raw = data.get("last_date")

    try:
        first = date.fromisoformat(
            str(first_raw)
        )
    except (TypeError, ValueError):
        return "не указано"

    last = None

    if last_raw:
        try:
            last = date.fromisoformat(
                str(last_raw)
            )
        except (TypeError, ValueError):
            last = None

    return format_ru_period(
        first,
        last,
    )
