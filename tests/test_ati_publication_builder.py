from datetime import date

from app.data_models.ati_publication import (
    AtiPublicationBuildInput,
    LoadingDateType,
    PublicationProfile,
    ResolvedRoutePoint,
)
from app.data_models.request import (
    TransportRequest,
)
from app.services.ati_publication_builder import (
    build_ati_publication,
)


def common_input(
    request: TransportRequest,
    route: list[ResolvedRoutePoint],
    **kwargs,
) -> AtiPublicationBuildInput:
    defaults = {
        "external_id": "TL-ATI-TEST-001",
        "request": request,
        "resolved_route": route,
        "contact_ids": [7776989],
        "board_ids": ["test-board"],
        "body_type_ids": [999],
        "currency_type_id": 1,
        "loading_date_type": (
            LoadingDateType.READY
        ),
        "weight_tons": 1.8,
        "weight_confirmed": True,
    }

    defaults.update(kwargs)

    return AtiPublicationBuildInput(
        **defaults
    )


def test_single_vehicle_payload():
    request = TransportRequest(
        raw_text="#ЗАЯВКА",
        origin="Владивосток",
        destination="Москва",
        route_points=[
            "Владивосток",
            "Москва",
        ],
        vehicle="Toyota Camry",
        requested_rate=150_000,
        payment_type="наличными",
        is_valid_request=True,
    )

    result = build_ati_publication(
        common_input(
            request,
            [
                ResolvedRoutePoint(
                    name="Владивосток",
                    city_id=1,
                ),
                ResolvedRoutePoint(
                    name="Москва",
                    city_id=2,
                ),
            ],
            weight_tons=1.6,
        )
    )

    app = result.payload[
        "cargo_application"
    ]

    assert result.ready_for_api is True
    assert (
        result.profile
        == PublicationProfile.SINGLE_VEHICLE
    )

    assert app["truck"]["load_type"] == (
        "dont-care"
    )

    assert app["payment"]["cash"] == 150_000

    assert app["route"]["loading"][
        "cargos"
    ][0]["name"] == "Toyota Camry"

    assert app["contacts"] == [7776989]


def test_vehicle_list_with_waypoint():
    request = TransportRequest(
        raw_text="#ЗАЯВКА",
        origin="Москва",
        destination="Адыгея",
        route_points=[
            "Москва",
            "Ростов-на-Дону",
            "Адыгея",
        ],
        vehicle=(
            "3 Jetour X70\n"
            "1 Jetour T2\n"
            "2 Jetour T1"
        ),
        requested_rate=210_000,
        payment_type="с НДС",
        is_valid_request=True,
    )

    result = build_ati_publication(
        common_input(
            request,
            [
                ResolvedRoutePoint(
                    name="Москва",
                    city_id=10,
                ),
                ResolvedRoutePoint(
                    name="Ростов-на-Дону",
                    city_id=20,
                    kind="unloading",
                ),
                ResolvedRoutePoint(
                    name="Адыгея",
                    city_id=30,
                ),
            ],
            loading_date_type=(
                LoadingDateType.FROM_DATE
            ),
            first_date=date(
                2026,
                7,
                15,
            ),
            weight_tons=10.8,
        )
    )

    app = result.payload[
        "cargo_application"
    ]

    assert result.ready_for_api is True
    assert (
        result.profile
        == PublicationProfile.VEHICLE_LIST
    )

    assert (
        result.estimated_vehicle_count
        == 6
    )

    assert app["payment"][
        "rate_with_vat"
    ] == 210_000

    assert app["route"]["loading"][
        "dates"
    ]["first_date"] == "2026-07-15"

    assert app["route"]["way_points"] == [
        {
            "type": "unloading",
            "location": {
                "type": "manual",
                "city_id": 20,
            },
        }
    ]


def test_full_carrier_lot_payload():
    request = TransportRequest(
        raw_text="#ЗАЯВКА",
        origin="Владивосток",
        destination="Москва",
        route_points=[
            "Владивосток",
            "Москва",
        ],
        is_lot=True,
        vehicle=(
            "Лот автомобилей: требуется "
            "полный автовоз."
        ),
        requested_rate=1_300_000,
        payment_type="наличными",
        is_valid_request=True,
    )

    result = build_ati_publication(
        common_input(
            request,
            [
                ResolvedRoutePoint(
                    name="Владивосток",
                    city_id=1,
                ),
                ResolvedRoutePoint(
                    name="Москва",
                    city_id=2,
                ),
            ],
            weight_tons=15.0,
        )
    )

    app = result.payload[
        "cargo_application"
    ]

    assert result.ready_for_api is True
    assert (
        result.profile
        == PublicationProfile.FULL_CARRIER_LOT
    )

    assert app["truck"]["load_type"] == "ftl"
    assert app["truck"]["trucks_count"] == 1

    assert app["route"]["loading"][
        "cargos"
    ][0]["name"] == (
        "Лот автомобилей — полный автовоз"
    )

    assert "полезную площадь" in result.note
    assert "конфигурацию" in result.note

    # Наше слово «Лот» не должно попадать
    # в техническое lot_id API ATI.
    assert "lot_id" not in str(result.payload)


def test_missing_api_reference_data_blocks_publish():
    request = TransportRequest(
        raw_text="#ЗАЯВКА",
        origin="Москва",
        destination="Казань",
        route_points=[
            "Москва",
            "Казань",
        ],
        vehicle="Toyota Camry",
        requested_rate=100_000,
        payment_type="без НДС",
        is_valid_request=True,
    )

    result = build_ati_publication(
        AtiPublicationBuildInput(
            external_id="TL-ATI-TEST-002",
            request=request,
            resolved_route=[
                ResolvedRoutePoint(
                    name="Москва",
                    city_id=1,
                ),
                ResolvedRoutePoint(
                    name="Казань",
                    city_id=None,
                ),
            ],
            loading_date_type=None,
            weight_tons=None,
            weight_confirmed=False,
        )
    )

    assert result.ready_for_api is False

    assert "contact_ids" in (
        result.missing_fields
    )

    assert "board_ids" in (
        result.missing_fields
    )

    assert "body_type_ids" in (
        result.missing_fields
    )

    assert "currency_type_id" in (
        result.missing_fields
    )

    assert "loading_date_type" in (
        result.missing_fields
    )

    assert "weight_confirmation" in (
        result.missing_fields
    )

    assert (
        "resolved_route[1].city_id"
        in result.missing_fields
    )


def test_rate_request_without_fixed_price():
    request = TransportRequest(
        raw_text="#ЗАЯВКА",
        origin="Владивосток",
        destination="Москва",
        route_points=[
            "Владивосток",
            "Москва",
        ],
        vehicle="1 автомобиль",
        requested_rate=None,
        payment_type=None,
        is_valid_request=True,
    )

    result = build_ati_publication(
        common_input(
            request,
            [
                ResolvedRoutePoint(
                    name="Владивосток",
                    city_id=1,
                ),
                ResolvedRoutePoint(
                    name="Москва",
                    city_id=2,
                ),
            ],
            currency_type_id=None,
            loading_date_type=(
                LoadingDateType.RATE_REQUEST
            ),
        )
    )

    payment = result.payload[
        "cargo_application"
    ]["payment"]

    assert result.ready_for_api is True
    assert payment["type"] == "rate-request"

    assert (
        payment["rate_with_vat_available"]
        is True
    )

    assert (
        payment["rate_without_vat_available"]
        is True
    )

    assert payment["cash_available"] is True
