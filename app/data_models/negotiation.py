from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class NegotiationStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_REPLY = "awaiting_reply"
    NEGOTIATING = "negotiating"
    RATE_RECEIVED = "rate_received"
    AGREEMENT_PROPOSED = "agreement_proposed"
    AGREED = "agreed"
    DECLINED = "declined"
    CLOSED = "closed"
    ERROR = "error"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessagePurpose(str, Enum):
    INITIAL_RATE_REQUEST = "initial_rate_request"
    ASK_RATE = "ask_rate"
    ASK_DETAILS = "ask_details"
    COUNTEROFFER = "counteroffer"
    PROPOSE_ACCEPTANCE = "propose_acceptance"
    FOLLOW_UP = "follow_up"
    CLOSE = "close"
    GENERAL = "general"


class MessageDeliveryStatus(str, Enum):
    RECEIVED = "received"
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    SENT = "sent"
    DRY_RUN = "dry_run"
    BLOCKED = "blocked"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSUMED = "consumed"


class NegotiationAction(str, Enum):
    REQUEST_INITIAL_RATE = "request_initial_rate"
    ASK_RATE = "ask_rate"
    ASK_DETAILS = "ask_details"
    COUNTER = "counter"
    PROPOSE_ACCEPTANCE = "propose_acceptance"
    CLOSE_UNAVAILABLE = "close_unavailable"
    ESCALATE = "escalate"


class Carrier(BaseModel):
    ati_carrier_id: str
    name: str | None = None
    ati_conversation_id: str | None = None


class RouteContext(BaseModel):
    origin: str
    destination: str
    cargo: str
    ready_date: str | None = None
    vehicle_condition: str | None = None
    payment_type: str | None = None
    comment: str | None = None


class RateOffer(BaseModel):
    amount: int
    currency: str = "RUB"
    vat_mode: str | None = None
    payment_type: str | None = None
    transit_days: int | None = None
    loading_date: str | None = None
    conditions: list[str] = Field(default_factory=list)
    raw_text: str
    confidence: float = 0.0


class CarrierReplyAnalysis(BaseModel):
    availability: bool | None = None
    offer: RateOffer | None = None
    needs_clarification: bool = False
    raw_text: str


class NegotiationMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    direction: MessageDirection
    purpose: MessagePurpose = MessagePurpose.GENERAL
    text: str
    delivery_status: MessageDeliveryStatus
    external_message_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    approved_by: str | None = None


class NegotiationSession(BaseModel):
    id: str = Field(default_factory=lambda: new_id("neg"))
    carrier: Carrier
    route: RouteContext
    target_rate: int | None = None
    max_rate: int | None = None
    status: NegotiationStatus = NegotiationStatus.DRAFT
    messages: list[NegotiationMessage] = Field(default_factory=list)
    offers: list[RateOffer] = Field(default_factory=list)
    agreed_rate: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class NegotiationDecision(BaseModel):
    action: NegotiationAction
    purpose: MessagePurpose
    reason: str
    proposed_rate: int | None = None
    offer: RateOffer | None = None
    requires_approval: bool = True


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: new_id("approval"))
    negotiation_id: str
    message_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    approved_at: datetime | None = None
    approved_by: str | None = None
