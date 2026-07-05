from pydantic import BaseModel, Field


class TransportRequest(BaseModel):
    """Structured request extracted from MAX or another source."""

    source: str = "manual"
    raw_text: str
    origin: str | None = None
    destination: str | None = None
    vehicle: str | None = None
    ready_date: str | None = None
    vehicle_condition: str | None = None
    payment_type: str | None = None
    comment: str | None = None
    is_valid_request: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class AtiDraft(BaseModel):
    """Safe draft for future ATI publication. Never published while DRY_RUN=true."""

    title: str
    route: str | None = None
    cargo_description: str | None = None
    ready_date: str | None = None
    payment_type: str | None = None
    comment: str | None = None
    dry_run: bool = True
