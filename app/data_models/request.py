from pydantic import BaseModel, Field


class TransportRequest(BaseModel):
    """
    Structured transport request extracted from MAX
    or another source.
    """

    source: str = "manual"
    raw_text: str

    origin: str | None = None
    destination: str | None = None

    # All route points in their actual order.
    # Example:
    # Москва → Ростов → Минеральные Воды
    route_points: list[str] = Field(
        default_factory=list
    )

    # Original route text before normalization.
    route_raw: str | None = None

    # Explicit marker: the customer provides enough
    # vehicles to load one complete car carrier.
    is_lot: bool = False

    vehicle: str | None = None
    ready_date: str | None = None
    vehicle_condition: str | None = None

    requested_rate: int | None = None
    currency: str = "RUB"
    payment_type: str | None = None

    comment: str | None = None

    is_valid_request: bool = False
    missing_fields: list[str] = Field(
        default_factory=list
    )


class AtiDraft(BaseModel):
    """
    Safe ATI publication draft.

    It is never really published while DRY_RUN=true.
    """

    title: str
    route: str | None = None
    route_points: list[str] = Field(
        default_factory=list
    )

    is_lot: bool = False

    cargo_description: str | None = None
    ready_date: str | None = None

    requested_rate: int | None = None
    currency: str = "RUB"
    payment_type: str | None = None

    comment: str | None = None
    dry_run: bool = True
