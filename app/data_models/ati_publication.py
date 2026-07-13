from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.data_models.request import (
    TransportRequest,
)


class PublicationProfile(str, Enum):
    SINGLE_VEHICLE = "single_vehicle"
    VEHICLE_LIST = "vehicle_list"
    FULL_CARRIER_LOT = "full_carrier_lot"


class LoadingDateType(str, Enum):
    READY = "ready"
    FROM_DATE = "from-date"
    PERMANENT = "permanent"
    RATE_REQUEST = "rate-request"


class ResolvedRoutePoint(BaseModel):
    """
    One route point verified against the ATI
    geographical dictionary.

    For intermediate points, kind must be confirmed
    before real publication.
    """

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    city_id: int | None = Field(
        default=None,
        gt=0,
    )

    region: str | None = None
    country: str | None = None

    kind: Literal[
        "loading",
        "unloading",
        "customs",
        "go-through",
    ] | None = None


class AtiPublicationBuildInput(BaseModel):
    """
    Data needed to build the exact body for
    POST /v2/cargos.

    Paid ATI access is not required to construct
    and validate this object locally.
    """

    external_id: str = Field(
        min_length=1,
        max_length=250,
    )

    request: TransportRequest

    resolved_route: list[
        ResolvedRoutePoint
    ] = Field(
        min_length=2,
    )

    contact_ids: list[int] = Field(
        default_factory=list,
    )

    board_ids: list[str] = Field(
        default_factory=list,
    )

    body_type_ids: list[int] = Field(
        default_factory=list,
    )

    currency_type_id: int | None = Field(
        default=None,
        gt=0,
    )

    loading_date_type: (
        LoadingDateType | None
    ) = None

    first_date: date | None = None
    last_date: date | None = None

    permanent_periodicity: Literal[
        "everyday",
        "workdays",
    ] = "everyday"

    weight_tons: float | None = Field(
        default=None,
        gt=0,
        le=9999,
    )

    weight_confirmed: bool = False

    publication_mode: Literal[
        "now",
        "15m",
        "30m",
        "1h",
        "3h",
        "6h",
    ] = "now"

    payment_mode: Literal[
        "on-unloading",
        "delayed-payment",
    ] = "on-unloading"

    payment_delay_days: int | None = Field(
        default=None,
        ge=0,
    )

    hide_counter_offers: bool = True
    direct_offer: bool = False
    on_card: bool = False

    @field_validator(
        "contact_ids",
        "body_type_ids",
    )
    @classmethod
    def validate_positive_ids(
        cls,
        values: list[int],
    ) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError(
                "ATI identifiers must be positive"
            )

        return list(dict.fromkeys(values))

    @field_validator("board_ids")
    @classmethod
    def validate_board_ids(
        cls,
        values: list[str],
    ) -> list[str]:
        cleaned = [
            value.strip()
            for value in values
            if value.strip()
        ]

        return list(dict.fromkeys(cleaned))


class AtiPublicationBuildResult(BaseModel):
    profile: PublicationProfile

    payload: dict[str, Any]

    ready_for_api: bool = False

    missing_fields: list[str] = Field(
        default_factory=list,
    )

    warnings: list[str] = Field(
        default_factory=list,
    )

    estimated_vehicle_count: int | None = None
    weight_tons: float | None = None
    weight_is_estimated: bool = False

    cargo_name: str
    note: str
