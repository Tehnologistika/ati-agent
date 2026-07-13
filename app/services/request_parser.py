from __future__ import annotations

import re

from app.data_models.request import (
    TransportRequest,
)
from app.services.loading_schedule import (
    is_loading_schedule_text,
    normalize_loading_input,
)


ROUTE_SPLIT_RE = re.compile(
    r"\s*(?:—|–|→|->)\s*"
    r"|\s+-\s*"
    r"|\s*-\s+"
)

AMOUNT_RE = re.compile(
    r"(?<!\d)"
    r"("
    r"\d{1,3}(?:[ \u00a0]\d{3})+"
    r"|"
    r"\d{5,8}"
    r")"
    r"(?!\d)"
)

PAYMENT_HINT_RE = re.compile(
    r"\b(?:"
    r"нал(?:ичными)?"
    r"|безнал"
    r"|ндс"
    r"|руб(?:лей)?"
    r")\b"
    r"|₽",
    flags=re.IGNORECASE,
)


LOT_RE = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё0-9_])"
    r"лот"
    r"(?![A-Za-zА-Яа-яЁё0-9_])",
    flags=re.IGNORECASE,
)


LOT_CARGO_DESCRIPTION = (
    "Лот автомобилей: требуется полный автовоз. "
    "Заказчик подбирает состав автомобилей под "
    "полезную площадь, размер и конфигурацию "
    "конкретного автовоза."
)


# This dictionary is not the full geography database.
# It only expands frequent operational abbreviations.
# Full validation will be performed through ATI geo API.
PLACE_ALIASES = {
    "мск": "Москва",
    "москва": "Москва",

    "спб": "Санкт-Петербург",
    "с петербург": "Санкт-Петербург",
    "санкт петербург": "Санкт-Петербург",
    "питер": "Санкт-Петербург",

    "мин воды": "Минеральные Воды",
    "минводы": "Минеральные Воды",
    "минеральные воды": "Минеральные Воды",

    "н новгород": "Нижний Новгород",
    "нижний новгород": "Нижний Новгород",

    "ростов н д": "Ростов-на-Дону",
    "ростов на дону": "Ростов-на-Дону",

    "алма ата": "Алматы",
    "алматы": "Алматы",

    "нур султан": "Астана",
    "астана": "Астана",
}


METADATA_LABELS = [
    "Маршрут",
    "Направление",
    "Откуда",
    "Куда",
    "Загрузка",
    "Выгрузка",
    "Город загрузки",
    "Город выгрузки",
    "Авто",
    "Автомобиль",
    "Груз",
    "Машина",
    "Дата готовности",
    "Дата",
    "Готовность",
    "На ходу",
    "Состояние",
    "Оплата",
    "Форма оплаты",
    "Комментарий",
    "Примечание",
    "Цена",
    "Ставка",
]


def _prepare_lines(
    text: str,
) -> list[str]:
    """
    Remove empty lines and a standalone #ЗАЯВКА tag,
    while preserving the actual request text.
    """

    result: list[str] = []

    normalized = str(text or "").replace(
        "\r\n",
        "\n",
    )

    for raw_line in normalized.split("\n"):
        line = raw_line.strip()

        line = re.sub(
            r"^\s*#\s*заявка\b[\s:.-]*",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip()

        if line:
            result.append(line)

    return result


def _extract_labeled(
    lines: list[str],
    labels: list[str],
) -> tuple[str | None, int | None]:
    for index, line in enumerate(lines):
        for label in labels:
            pattern = (
                rf"^\s*{re.escape(label)}"
                rf"\s*[:\-]\s*(.+)$"
            )

            match = re.match(
                pattern,
                line,
                flags=re.IGNORECASE,
            )

            if match:
                return (
                    match.group(1).strip(),
                    index,
                )

    return None, None


def _alias_key(
    value: str,
) -> str:
    normalized = value.casefold().replace(
        "ё",
        "е",
    )

    normalized = re.sub(
        r"[./\\_-]+",
        " ",
        normalized,
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized.strip()


def _clean_place(
    value: str,
) -> str:
    """
    Remove route annotations such as "(2 погрузки)"
    but preserve the original route separately.
    """

    cleaned = re.sub(
        r"\s*\([^)]*\)\s*",
        " ",
        str(value or ""),
    )

    cleaned = re.sub(
        r"^\s*(?:г(?:ород)?\.?\s+)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned,
    ).strip(" ,;:.")

    alias = PLACE_ALIASES.get(
        _alias_key(cleaned)
    )

    return alias or cleaned


def _split_route(
    route: str,
) -> list[str]:
    parts = ROUTE_SPLIT_RE.split(
        str(route or "").strip()
    )

    result = [
        _clean_place(part)
        for part in parts
        if part.strip()
    ]

    return [
        item
        for item in result
        if item
    ]


def _is_rate_line(
    line: str,
) -> bool:
    match = AMOUNT_RE.search(line)

    if not match:
        return False

    # Подписанная стоимость является ставкой
    # даже без слов «нал», «НДС», «руб.» или знака ₽.
    if re.match(
        r"^\s*(?:ставка|цена|стоимость)"
        r"\s*[:\-]",
        line,
        flags=re.IGNORECASE,
    ):
        return True

    if PAYMENT_HINT_RE.search(line):
        return True

    remainder = AMOUNT_RE.sub(
        "",
        line,
        count=1,
    )

    remainder = re.sub(
        r"[\s.,:;₽]+",
        "",
        remainder,
    )

    return not remainder


def _looks_like_route(
    line: str,
) -> bool:
    if _is_rate_line(line):
        return False

    points = _split_route(line)

    if len(points) < 2:
        return False

    for point in points:
        if re.match(r"^\d", point):
            return False

        if not re.search(
            r"[A-Za-zА-Яа-яЁё]",
            point,
        ):
            return False

    return True


def _find_route(
    lines: list[str],
) -> tuple[
    str | None,
    str | None,
    list[str],
    str | None,
    int | None,
]:
    labeled_route, route_index = (
        _extract_labeled(
            lines,
            [
                "Маршрут",
                "Направление",
            ],
        )
    )

    if labeled_route:
        route_points = _split_route(
            labeled_route
        )

        if len(route_points) >= 2:
            return (
                route_points[0],
                route_points[-1],
                route_points,
                labeled_route,
                route_index,
            )

    origin, origin_index = _extract_labeled(
        lines,
        [
            "Откуда",
            "Загрузка",
            "Город загрузки",
        ],
    )

    destination, destination_index = (
        _extract_labeled(
            lines,
            [
                "Куда",
                "Выгрузка",
                "Город выгрузки",
            ],
        )
    )

    if origin or destination:
        cleaned_origin = (
            _clean_place(origin)
            if origin
            else None
        )

        cleaned_destination = (
            _clean_place(destination)
            if destination
            else None
        )

        points = [
            point
            for point in [
                cleaned_origin,
                cleaned_destination,
            ]
            if point
        ]

        indexes = [
            index
            for index in [
                origin_index,
                destination_index,
            ]
            if index is not None
        ]

        return (
            cleaned_origin,
            cleaned_destination,
            points,
            " — ".join(points) or None,
            max(indexes) if indexes else None,
        )

    for index, line in enumerate(lines):
        if not _looks_like_route(line):
            continue

        points = _split_route(line)

        return (
            points[0],
            points[-1],
            points,
            line,
            index,
        )

    return None, None, [], None, None


def _is_metadata_line(
    line: str,
) -> bool:
    for label in METADATA_LABELS:
        if re.match(
            rf"^\s*{re.escape(label)}\s*[:\-]",
            line,
            flags=re.IGNORECASE,
        ):
            return True

    return False


def _is_lot_request(
    lines: list[str],
) -> bool:
    """
    Detect an explicit standalone word ЛОТ.

    Similar words such as «лоток» or «лотос»
    must not activate the full-car-carrier mode.
    """

    return any(
        LOT_RE.search(line)
        for line in lines
    )


def _extract_ready_date(
    lines: list[str],
) -> str | None:
    labeled, _ = _extract_labeled(
        lines,
        [
            "Дата готовности",
            "Дата",
            "Готовность",
        ],
    )

    if labeled:
        return normalize_loading_input(
            labeled
        )

    for line in lines:
        if is_loading_schedule_text(line):
            return normalize_loading_input(
                line
            )

    return None


def _extract_vehicle(
    lines: list[str],
    route_index: int | None,
) -> str | None:
    labeled, _ = _extract_labeled(
        lines,
        [
            "Авто",
            "Автомобиль",
            "Груз",
            "Машина",
        ],
    )

    if labeled:
        return labeled

    if route_index is None:
        return None

    vehicle_lines: list[str] = []

    for line in lines[route_index + 1:]:
        if _is_rate_line(line):
            break

        if _is_metadata_line(line):
            continue

        if is_loading_schedule_text(line):
            continue

        if _looks_like_route(line):
            continue

        if re.fullmatch(
            r"(?:"
            r"на ходу"
            r"|не на ходу"
            r"|аварийн(?:ая|ый|ое)"
            r")",
            line,
            flags=re.IGNORECASE,
        ):
            continue

        if PAYMENT_HINT_RE.fullmatch(
            line.strip()
        ):
            continue

        vehicle_lines.append(line)

    if not vehicle_lines:
        return None

    return "\n".join(vehicle_lines)


def _extract_rate(
    lines: list[str],
) -> int | None:
    for line in lines:
        if not _is_rate_line(line):
            continue

        match = AMOUNT_RE.search(line)

        if not match:
            continue

        digits = re.sub(
            r"\D",
            "",
            match.group(1),
        )

        if digits:
            return int(digits)

    return None


def _infer_payment(
    lines: list[str],
) -> str | None:
    combined = "\n".join(lines)

    patterns = [
        (
            r"\bбез\s*ндс\b",
            "без НДС",
        ),
        (
            r"\bс\s*ндс\b",
            "с НДС",
        ),
        (
            r"\bбезнал(?:ичный|ом|ом расчёте)?\b",
            "безнал",
        ),
        (
            r"\bналичными\b",
            "наличными",
        ),
        (
            r"\bнал\b",
            "наличные",
        ),
    ]

    for pattern, result in patterns:
        if re.search(
            pattern,
            combined,
            flags=re.IGNORECASE,
        ):
            return result

    return None


def parse_transport_request(
    raw_text: str,
    source: str = "manual",
) -> TransportRequest:
    """
    Parse both labelled and free-form MAX requests.

    The parser does not publish or send anything.
    Geographic validation is performed separately.
    """

    lines = _prepare_lines(raw_text)

    (
        origin,
        destination,
        route_points,
        route_raw,
        route_index,
    ) = _find_route(lines)

    vehicle = _extract_vehicle(
        lines,
        route_index,
    )

    is_lot = _is_lot_request(lines)

    if is_lot:
        # For a full-car-carrier lot the exact makes,
        # models and fixed vehicle count are optional.
        vehicle = LOT_CARGO_DESCRIPTION

    ready_date = _extract_ready_date(
        lines
    )

    condition, _ = _extract_labeled(
        lines,
        [
            "На ходу",
            "Состояние",
        ],
    )

    payment, _ = _extract_labeled(
        lines,
        [
            "Оплата",
            "Форма оплаты",
        ],
    )

    payment = payment or _infer_payment(lines)

    comment, _ = _extract_labeled(
        lines,
        [
            "Комментарий",
            "Примечание",
        ],
    )

    request = TransportRequest(
        source=source,
        raw_text=raw_text,
        origin=origin,
        destination=destination,
        route_points=route_points,
        route_raw=route_raw,
        is_lot=is_lot,
        vehicle=vehicle,
        ready_date=ready_date,
        vehicle_condition=condition,
        requested_rate=_extract_rate(lines),
        currency="RUB",
        payment_type=payment,
        comment=comment,
        is_valid_request=bool(
            re.search(
                r"#?\s*заявка\b",
                raw_text,
                flags=re.IGNORECASE,
            )
        ),
    )

    required = {
        "origin": request.origin,
        "destination": request.destination,
        "vehicle": request.vehicle,
    }

    request.missing_fields = [
        name
        for name, value in required.items()
        if not value
    ]

    if request.missing_fields:
        request.is_valid_request = False

    return request
