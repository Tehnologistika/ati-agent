from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.data_models.ati_publication import (
    LoadingDateType,
)


MONTHS = {
    "январь": 1,
    "января": 1,
    "февраль": 2,
    "февраля": 2,
    "март": 3,
    "марта": 3,
    "апрель": 4,
    "апреля": 4,
    "май": 5,
    "мая": 5,
    "июнь": 6,
    "июня": 6,
    "июль": 7,
    "июля": 7,
    "август": 8,
    "августа": 8,
    "сентябрь": 9,
    "сентября": 9,
    "октябрь": 10,
    "октября": 10,
    "ноябрь": 11,
    "ноября": 11,
    "декабрь": 12,
    "декабря": 12,
}


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


READY_RE = re.compile(
    r"^(?:"
    r"(?:(?:авто|автомобиль|машина|лот|"
    r"автомобили|машины)\s+)?"
    r"готов(?:а|о|ы)?"
    r"(?:\s+к\s+(?:отправке|погрузке|загрузке))?"
    r"|можно\s+(?:грузить|загружать)"
    r")$",
    flags=re.IGNORECASE,
)


PERMANENT_RE = re.compile(
    r"^(?:"
    r"постоянно"
    r"|постоянная\s+загрузка"
    r"|регулярно"
    r"|ежедневно"
    r")$",
    flags=re.IGNORECASE,
)


RATE_REQUEST_RE = re.compile(
    r"^(?:"
    r"запрос\s+ставки"
    r"|расч[её]т\s+ставки"
    r"|груза\s+(?:пока\s+)?нет"
    r"|только\s+расч[её]т"
    r")$",
    flags=re.IGNORECASE,
)


class LoadingSchedule(BaseModel):
    raw_value: str | None = None
    normalized_text: str | None = None

    date_type: LoadingDateType | None = None

    first_date: date | None = None
    last_date: date | None = None

    periodicity: Literal[
        "everyday",
        "workdays",
    ] = "everyday"


def moscow_today() -> date:
    return datetime.now(
        ZoneInfo("Europe/Moscow")
    ).date()


def _clean(value: str | None) -> str:
    text = str(value or "").strip()

    text = (
        text
        .replace("—", "-")
        .replace("–", "-")
        .replace("−", "-")
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text.strip(" .,!;:")


def _normalized(value: str | None) -> str:
    return (
        _clean(value)
        .casefold()
        .replace("ё", "е")
    )


def _normalize_year(
    value: str | None,
) -> int | None:
    if not value:
        return None

    year = int(value)

    if year < 100:
        year += 2000

    return year


def _safe_date(
    year: int,
    month: int,
    day: int,
) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_first(
    day: int,
    month: int,
    year: int | None,
    today: date,
) -> date | None:
    if year is not None:
        return _safe_date(
            year,
            month,
            day,
        )

    result = _safe_date(
        today.year,
        month,
        day,
    )

    if result is None:
        return None

    if result < today:
        result = _safe_date(
            today.year + 1,
            month,
            day,
        )

    return result


def _resolve_last(
    day: int,
    month: int,
    year: int | None,
    first: date,
) -> date | None:
    if year is not None:
        return _safe_date(
            year,
            month,
            day,
        )

    result = _safe_date(
        first.year,
        month,
        day,
    )

    if result is None:
        return None

    if result < first:
        result = _safe_date(
            first.year + 1,
            month,
            day,
        )

    return result


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


def _from_date(
    raw_value: str,
    first: date,
    last: date | None = None,
) -> LoadingSchedule:
    return LoadingSchedule(
        raw_value=raw_value,
        normalized_text=format_ru_period(
            first,
            last,
        ),
        date_type=LoadingDateType.FROM_DATE,
        first_date=first,
        last_date=last,
    )


def parse_loading_schedule(
    value: str | None,
    *,
    today: date | None = None,
) -> LoadingSchedule:
    raw = _clean(value)

    if not raw:
        return LoadingSchedule()

    current = today or moscow_today()
    normalized = _normalized(raw)

    if READY_RE.fullmatch(normalized):
        return LoadingSchedule(
            raw_value=raw,
            normalized_text="Готово к отправке",
            date_type=LoadingDateType.READY,
        )

    if normalized in {
        "сегодня",
        "сейчас",
    }:
        return LoadingSchedule(
            raw_value=raw,
            normalized_text="Готово к отправке",
            date_type=LoadingDateType.READY,
        )

    if normalized == "завтра":
        return _from_date(
            raw,
            current + timedelta(days=1),
        )

    if normalized in {
        "в течение недели",
        "в течении недели",
        "на ближайшей неделе",
    }:
        return _from_date(
            raw,
            current,
            current + timedelta(days=7),
        )

    if PERMANENT_RE.fullmatch(normalized):
        return LoadingSchedule(
            raw_value=raw,
            normalized_text="Постоянная загрузка",
            date_type=LoadingDateType.PERMANENT,
        )

    if RATE_REQUEST_RE.fullmatch(normalized):
        return LoadingSchedule(
            raw_value=raw,
            normalized_text="Запрос ставки",
            date_type=LoadingDateType.RATE_REQUEST,
        )

    iso_match = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})",
        normalized,
    )

    if iso_match:
        target = _safe_date(
            int(iso_match.group(1)),
            int(iso_match.group(2)),
            int(iso_match.group(3)),
        )

        if target:
            return _from_date(raw, target)

    numeric_range = re.fullmatch(
        r"(\d{1,2})[./](\d{1,2})"
        r"(?:[./](\d{2,4}))?"
        r"\s*-\s*"
        r"(\d{1,2})[./](\d{1,2})"
        r"(?:[./](\d{2,4}))?",
        normalized,
    )

    if numeric_range:
        first = _resolve_first(
            int(numeric_range.group(1)),
            int(numeric_range.group(2)),
            _normalize_year(
                numeric_range.group(3)
            ),
            current,
        )

        if first:
            last = _resolve_last(
                int(numeric_range.group(4)),
                int(numeric_range.group(5)),
                _normalize_year(
                    numeric_range.group(6)
                ),
                first,
            )

            if last and last >= first:
                return _from_date(
                    raw,
                    first,
                    last,
                )

    numeric_single = re.fullmatch(
        r"(\d{1,2})[./](\d{1,2})"
        r"(?:[./](\d{2,4}))?",
        normalized,
    )

    if numeric_single:
        target = _resolve_first(
            int(numeric_single.group(1)),
            int(numeric_single.group(2)),
            _normalize_year(
                numeric_single.group(3)
            ),
            current,
        )

        if target:
            return _from_date(raw, target)

    same_month_range = re.fullmatch(
        r"(?:с\s+)?"
        r"(\d{1,2})\s*"
        r"(?:-|по)\s*"
        r"(\d{1,2})\s+"
        r"([а-я]+)"
        r"(?:\s+(\d{4}))?"
        r"(?:\s*г\.?)?",
        normalized,
    )

    if same_month_range:
        month = MONTHS.get(
            same_month_range.group(3)
        )

        year = _normalize_year(
            same_month_range.group(4)
        )

        if month:
            first = _resolve_first(
                int(same_month_range.group(1)),
                month,
                year,
                current,
            )

            if first:
                last = _resolve_last(
                    int(same_month_range.group(2)),
                    month,
                    year,
                    first,
                )

                if last and last >= first:
                    return _from_date(
                        raw,
                        first,
                        last,
                    )

    full_text_range = re.fullmatch(
        r"(?:с\s+)?"
        r"(\d{1,2})\s+([а-я]+)"
        r"(?:\s+(\d{4}))?"
        r"\s*(?:-|по)\s*"
        r"(\d{1,2})\s+([а-я]+)"
        r"(?:\s+(\d{4}))?"
        r"(?:\s*г\.?)?",
        normalized,
    )

    if full_text_range:
        first_month = MONTHS.get(
            full_text_range.group(2)
        )

        last_month = MONTHS.get(
            full_text_range.group(5)
        )

        if first_month and last_month:
            first = _resolve_first(
                int(full_text_range.group(1)),
                first_month,
                _normalize_year(
                    full_text_range.group(3)
                ),
                current,
            )

            if first:
                last = _resolve_last(
                    int(full_text_range.group(4)),
                    last_month,
                    _normalize_year(
                        full_text_range.group(6)
                    ),
                    first,
                )

                if last and last >= first:
                    return _from_date(
                        raw,
                        first,
                        last,
                    )

    text_single = re.fullmatch(
        r"(\d{1,2})\s+([а-я]+)"
        r"(?:\s+(\d{4}))?"
        r"(?:\s*г\.?)?",
        normalized,
    )

    if text_single:
        month = MONTHS.get(
            text_single.group(2)
        )

        if month:
            target = _resolve_first(
                int(text_single.group(1)),
                month,
                _normalize_year(
                    text_single.group(3)
                ),
                current,
            )

            if target:
                return _from_date(
                    raw,
                    target,
                )

    return LoadingSchedule(
        raw_value=raw,
        normalized_text=raw,
    )


def is_loading_schedule_text(
    value: str | None,
) -> bool:
    return (
        parse_loading_schedule(value).date_type
        is not None
    )


def normalize_loading_input(
    value: str | None,
) -> str | None:
    return parse_loading_schedule(
        value
    ).normalized_text
