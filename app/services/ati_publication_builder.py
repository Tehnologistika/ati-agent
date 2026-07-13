from __future__ import annotations

import re
from typing import Any

from app.data_models.ati_publication import (
    AtiPublicationBuildInput,
    AtiPublicationBuildResult,
    LoadingDateType,
    PublicationProfile,
    ResolvedRoutePoint,
)


PROFILE_LABELS = {
    PublicationProfile.SINGLE_VEHICLE: (
        "одно или штучное авто"
    ),
    PublicationProfile.VEHICLE_LIST: (
        "список автомобилей"
    ),
    PublicationProfile.FULL_CARRIER_LOT: (
        "лот — полный автовоз"
    ),
}


WAYPOINT_LABELS = {
    "loading": "погрузка",
    "unloading": "выгрузка",
    "customs": "таможня",
    "go-through": "следование через пункт",
}


def _vehicle_count(
    description: str | None,
) -> int | None:
    text = str(description or "").strip()

    if not text:
        return None

    generic = re.search(
        r"(?im)^\s*(\d+)\s*"
        r"(?:авто|автомобил(?:ь|я|ей))\b",
        text,
    )

    if generic:
        return int(generic.group(1))

    total = 0
    matched_lines = 0

    for line in text.splitlines():
        match = re.match(
            r"^\s*(\d+)\s+\S+",
            line,
        )

        if not match:
            continue

        total += int(match.group(1))
        matched_lines += 1

    if matched_lines:
        return total

    return 1


def _detect_profile(
    data: AtiPublicationBuildInput,
    vehicle_count: int | None,
) -> PublicationProfile:
    if data.request.is_lot:
        return (
            PublicationProfile
            .FULL_CARRIER_LOT
        )

    if (
        vehicle_count is not None
        and vehicle_count > 1
    ):
        return PublicationProfile.VEHICLE_LIST

    return PublicationProfile.SINGLE_VEHICLE


def _estimated_weight(
    profile: PublicationProfile,
    vehicle_count: int | None,
) -> float:
    if (
        profile
        == PublicationProfile.FULL_CARRIER_LOT
    ):
        return 15.0

    count = max(
        1,
        vehicle_count or 1,
    )

    return round(
        min(15.0, count * 1.8),
        1,
    )


def _cargo_name(
    profile: PublicationProfile,
    description: str | None,
    vehicle_count: int | None,
) -> str:
    if (
        profile
        == PublicationProfile.FULL_CARRIER_LOT
    ):
        return (
            "Лот автомобилей — полный автовоз"
        )

    if (
        profile
        == PublicationProfile.VEHICLE_LIST
    ):
        if vehicle_count:
            return (
                f"Автомобили — "
                f"{vehicle_count} ед."
            )

        return "Автомобили"

    cleaned = " ".join(
        str(description or "").split()
    )

    if not cleaned:
        return "Автомобиль"

    return cleaned[:200]


def _payment_payload(
    data: AtiPublicationBuildInput,
    missing: list[str],
) -> dict[str, Any]:
    request = data.request

    common: dict[str, Any] = {
        "hide_counter_offers": (
            data.hide_counter_offers
        ),
        "direct_offer": data.direct_offer,
        "prepayment": {
            "percent": 0,
            "using_fuel": False,
        },
        "payment_mode": {
            "type": data.payment_mode,
        },
    }

    if (
        data.payment_mode
        == "delayed-payment"
    ):
        if data.payment_delay_days is None:
            missing.append(
                "payment_delay_days"
            )
        else:
            common["payment_mode"][
                "payment_delay_days"
            ] = data.payment_delay_days

    if request.requested_rate is None:
        return {
            "type": "rate-request",
            "rate_with_vat_available": True,
            "rate_without_vat_available": True,
            "cash_available": True,
            **common,
        }

    if data.currency_type_id is None:
        missing.append("currency_type_id")

    payment: dict[str, Any] = {
        "type": "with-bargaining",
        "currency_type": (
            data.currency_type_id
        ),
        "on_card": data.on_card,
        **common,
    }

    normalized = str(
        request.payment_type or ""
    ).casefold().replace("ё", "е")

    if re.search(
        r"\bбез\s*ндс\b",
        normalized,
    ):
        payment["rate_without_vat"] = (
            request.requested_rate
        )

    elif re.search(
        r"\bс\s*ндс\b",
        normalized,
    ):
        payment["rate_with_vat"] = (
            request.requested_rate
        )

    elif re.search(
        r"\bнал(?:ичными)?\b",
        normalized,
    ):
        payment["cash"] = (
            request.requested_rate
        )

    else:
        missing.append("payment_type")

    return payment


def _loading_dates(
    data: AtiPublicationBuildInput,
    missing: list[str],
) -> dict[str, Any]:
    date_type = data.loading_date_type

    if date_type is None:
        missing.append("loading_date_type")

        return {
            "type": "ready",
        }

    if date_type == LoadingDateType.READY:
        return {
            "type": "ready",
        }

    if date_type == LoadingDateType.RATE_REQUEST:
        return {
            "type": "rate-request",
        }

    if date_type == LoadingDateType.PERMANENT:
        return {
            "type": "permanent",
            "periodicity": (
                data.permanent_periodicity
            ),
        }

    if data.first_date is None:
        missing.append("first_date")

    result: dict[str, Any] = {
        "type": "from-date",
        "first_date": (
            data.first_date.isoformat()
            if data.first_date
            else None
        ),
    }

    if data.last_date:
        result["last_date"] = (
            data.last_date.isoformat()
        )

    return result


def _location(
    point: ResolvedRoutePoint,
) -> dict[str, Any]:
    return {
        "type": "manual",
        "city_id": point.city_id,
    }


def _build_note(
    data: AtiPublicationBuildInput,
    profile: PublicationProfile,
    cargo_name: str,
    vehicle_count: int | None,
    weight_tons: float,
) -> str:
    request = data.request

    route_text = " — ".join(
        point.name
        for point in data.resolved_route
    )

    lines = [
        (
            f"Маршрут: {route_text}."
        ),
        (
            "Тип заявки: "
            f"{PROFILE_LABELS[profile]}."
        ),
    ]

    if (
        profile
        == PublicationProfile.FULL_CARRIER_LOT
    ):
        lines.extend(
            [
                (
                    "Требуется один полный "
                    "автовоз."
                ),
                (
                    "Заказчик располагает "
                    "достаточным количеством "
                    "автомобилей и сформирует "
                    "состав загрузки под полезную "
                    "площадь, вместимость и "
                    "конфигурацию конкретного "
                    "автовоза."
                ),
                (
                    "Количество и размеры "
                    "автомобилей согласовываются "
                    "с перевозчиком перед "
                    "погрузкой."
                ),
            ]
        )
    else:
        lines.append(
            f"Груз: {cargo_name}."
        )

        if request.vehicle:
            lines.append(
                "Состав: "
                f"{request.vehicle.strip()}."
            )

        if vehicle_count:
            lines.append(
                "Количество автомобилей: "
                f"{vehicle_count}."
            )

    lines.append(
        "Ориентировочный общий вес: "
        f"{weight_tons:g} т."
    )

    if request.vehicle_condition:
        lines.append(
            "Состояние: "
            f"{request.vehicle_condition}."
        )

    if request.requested_rate is not None:
        rate = (
            f"{request.requested_rate:,}"
            .replace(",", " ")
        )

        payment = (
            request.payment_type
            or "форма оплаты уточняется"
        )

        lines.append(
            f"Ставка: {rate} ₽, {payment}."
        )
    else:
        lines.append(
            "Просим предложить ставку."
        )

    if request.comment:
        lines.append(
            f"Дополнительно: "
            f"{request.comment.strip()}."
        )

    lines.append(
        "Связь и предложения — через ATI."
    )

    note = "\n".join(lines)

    return note[:1000]


def build_ati_publication(
    data: AtiPublicationBuildInput,
) -> AtiPublicationBuildResult:
    """
    Build a real ATI /v2/cargos request body.

    This function performs no network requests.
    """

    missing: list[str] = []
    warnings: list[str] = []

    request = data.request

    if not request.is_valid_request:
        missing.append(
            "request_validation"
        )

    route = data.resolved_route

    if (
        request.route_points
        and len(route)
        != len(request.route_points)
    ):
        missing.append(
            "resolved_route_length"
        )

    for index, point in enumerate(route):
        if point.city_id is None:
            missing.append(
                f"resolved_route[{index}].city_id"
            )

        if (
            0 < index < len(route) - 1
            and point.kind is None
        ):
            missing.append(
                f"resolved_route[{index}].kind"
            )

    vehicle_count = _vehicle_count(
        request.vehicle
    )

    profile = _detect_profile(
        data,
        vehicle_count,
    )

    cargo_name = _cargo_name(
        profile,
        request.vehicle,
        vehicle_count,
    )

    weight_is_estimated = (
        data.weight_tons is None
    )

    weight_tons = (
        data.weight_tons
        if data.weight_tons is not None
        else _estimated_weight(
            profile,
            vehicle_count,
        )
    )

    if weight_is_estimated:
        warnings.append(
            "Вес рассчитан ориентировочно "
            "и должен быть подтверждён."
        )

        if not data.weight_confirmed:
            missing.append(
                "weight_confirmation"
            )

    if not data.contact_ids:
        missing.append("contact_ids")

    if not data.board_ids:
        missing.append("board_ids")

    if not data.body_type_ids:
        missing.append("body_type_ids")

    loading_dates = _loading_dates(
        data,
        missing,
    )

    payment = _payment_payload(
        data,
        missing,
    )

    cargo = {
        "id": 1,
        "name": cargo_name,
        "weight": {
            "type": "tons",
            "quantity": weight_tons,
        },
    }

    loading = {
        "location": _location(route[0]),
        "dates": loading_dates,
        "cargos": [cargo],
    }

    unloading = {
        "location": _location(route[-1]),
    }

    way_points = []

    for point in route[1:-1]:
        way_points.append(
            {
                "type": (
                    point.kind
                    or "go-through"
                ),
                "location": _location(point),
            }
        )

    load_type = (
        "ftl"
        if profile
        == PublicationProfile.FULL_CARRIER_LOT
        else "dont-care"
    )

    truck = {
        "trucks_count": 1,
        "load_type": load_type,
        "body_types": data.body_type_ids,
        "is_tracking": False,
        "required_capacity": weight_tons,
    }

    boards = [
        {
            "id": board_id,
            "publication_mode": (
                data.publication_mode
            ),
            "cancel_publish_on_auction_bet": (
                False
            ),
            "reservation_enabled": False,
        }
        for board_id in data.board_ids
    ]

    note = _build_note(
        data,
        profile,
        cargo_name,
        vehicle_count,
        weight_tons,
    )

    payload = {
        "cargo_application": {
            "external_id": data.external_id,
            "route": {
                "loading": loading,
                "unloading": unloading,
                "way_points": way_points,
            },
            "truck": truck,
            "payment": payment,
            "boards": boards,
            "note": note,
            "contacts": data.contact_ids,
        }
    }

    unique_missing = list(
        dict.fromkeys(missing)
    )

    return AtiPublicationBuildResult(
        profile=profile,
        payload=payload,
        ready_for_api=not unique_missing,
        missing_fields=unique_missing,
        warnings=warnings,
        estimated_vehicle_count=vehicle_count,
        weight_tons=weight_tons,
        weight_is_estimated=(
            weight_is_estimated
        ),
        cargo_name=cargo_name,
        note=note,
    )
