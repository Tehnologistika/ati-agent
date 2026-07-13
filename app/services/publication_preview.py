from __future__ import annotations

from app.config import Settings
from app.data_models.ati_publication import (
    AtiPublicationBuildInput,
    AtiPublicationBuildResult,
    LoadingDateType,
    ResolvedRoutePoint,
)
from app.data_models.request import (
    TransportRequest,
)
from app.services.ati_publication_builder import (
    build_ati_publication,
)


def _contact_ids(
    settings: Settings,
) -> list[int]:
    value = str(
        settings.ati_contact_id or ""
    ).strip()

    if not value:
        return []

    try:
        contact_id = int(value)
    except ValueError:
        return []

    if contact_id <= 0:
        return []

    return [contact_id]


def _route_names(
    request: TransportRequest,
) -> list[str]:
    names = [
        str(value).strip()
        for value in request.route_points
        if str(value).strip()
    ]

    if len(names) >= 2:
        return names

    fallback = [
        str(value).strip()
        for value in [
            request.origin,
            request.destination,
        ]
        if str(value or "").strip()
    ]

    return fallback


def _loading_date_type(
    request: TransportRequest,
) -> LoadingDateType | None:
    value = str(
        request.ready_date or ""
    ).strip().casefold().replace(
        "ё",
        "е",
    )

    if not value:
        return None

    if (
        "груза нет" in value
        or "запрос ставки" in value
    ):
        return LoadingDateType.RATE_REQUEST

    if "постоян" in value:
        return LoadingDateType.PERMANENT

    if (
        "готов" in value
        or value in {
            "сегодня",
            "сейчас",
        }
    ):
        return LoadingDateType.READY

    # Конкретные даты и диапазоны будут
    # разбираться отдельным модулем дат.
    return None


def build_publication_preview(
    request: TransportRequest,
    approval_id: str,
    settings: Settings,
) -> AtiPublicationBuildResult:
    """
    Build the exact future ATI payload locally.

    The function performs no HTTP requests and does
    not require paid ATI services.
    """

    route_names = _route_names(request)

    if len(route_names) < 2:
        raise ValueError(
            "At least two route points are required"
        )

    resolved_route: list[
        ResolvedRoutePoint
    ] = []

    for index, name in enumerate(route_names):
        intermediate = (
            0 < index < len(route_names) - 1
        )

        resolved_route.append(
            ResolvedRoutePoint(
                name=name,
                city_id=None,
                kind=None if intermediate else None,
            )
        )

    external_suffix = (
        str(approval_id)
        .replace("publication-", "")
        .upper()
    )

    external_id = (
        f"TL-ATI-{external_suffix}"
    )[:250]

    build_input = AtiPublicationBuildInput(
        external_id=external_id,
        request=request,
        resolved_route=resolved_route,

        # Контакт можно подготовить заранее.
        contact_ids=_contact_ids(settings),

        # Значения справочников будут заполнены
        # после подключения ATI.
        board_ids=[],
        body_type_ids=[],
        currency_type_id=None,

        loading_date_type=(
            _loading_date_type(request)
        ),

        # Пока вес рассчитывается ориентировочно.
        weight_tons=None,
        weight_confirmed=False,

        publication_mode="now",
        payment_mode="on-unloading",

        hide_counter_offers=True,
        direct_offer=False,
        on_card=False,
    )

    return build_ati_publication(
        build_input
    )
