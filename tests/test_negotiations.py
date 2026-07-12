import pytest

from app.config import Settings
from app.data_models.negotiation import (
    Carrier,
    MessageDeliveryStatus,
    MessageDirection,
    NegotiationAction,
    NegotiationMessage,
    NegotiationSession,
    RouteContext,
)
from app.integrations.ati_messenger_client import AtiMessengerClient
from app.negotiation_orchestrator import NegotiationOrchestrator
from app.services.negotiation_policy import NegotiationPolicy
from app.services.negotiation_repository import NegotiationRepository
from app.services.rate_parser import analyze_carrier_reply


def _session(target=800_000, maximum=900_000):
    return NegotiationSession(
        carrier=Carrier(ati_carrier_id="carrier-1"),
        route=RouteContext(origin="Владивосток", destination="Новосибирск", cargo="8 автомобилей"),
        target_rate=target,
        max_rate=maximum,
    )


def test_parse_spaced_ruble_rate_and_conditions():
    result = analyze_carrier_reply("Актуально. 850 000 нал без НДС, доставим за 3 дня")
    assert result.availability is True
    assert result.offer is not None
    assert result.offer.amount == 850_000
    assert result.offer.currency == "RUB"
    assert result.offer.payment_type == "cash"
    assert result.offer.vat_mode == "without_vat"
    assert result.offer.transit_days == 3


def test_parse_million_rate():
    result = analyze_carrier_reply("Ставка 1,2 млн рублей с НДС")
    assert result.offer is not None
    assert result.offer.amount == 1_200_000
    assert result.offer.vat_mode == "with_vat"


def test_unavailable_reply_has_no_offer():
    result = analyze_carrier_reply("Уже загрузился, машина неактуальна")
    assert result.availability is False
    assert result.offer is None


def test_rate_above_maximum_gets_counteroffer():
    decision = NegotiationPolicy().decide(_session(), "Можем за 950 000 рублей")
    assert decision.action == NegotiationAction.COUNTER
    assert decision.proposed_rate == 800_000


def test_rate_at_target_gets_acceptance_proposal():
    decision = NegotiationPolicy().decide(_session(), "Готовы за 800 000 рублей")
    assert decision.action == NegotiationAction.PROPOSE_ACCEPTANCE
    assert decision.proposed_rate == 800_000


def test_missing_rate_requests_rate():
    decision = NegotiationPolicy().decide(_session(), "Машина есть, могу загрузиться завтра")
    assert decision.action == NegotiationAction.ASK_RATE


def test_ati_message_is_blocked_by_dry_run():
    client = AtiMessengerClient(Settings(dry_run=True, ati_mode="APPROVAL_REQUIRED"))
    result = client.send_message("dialog-1", "Тест", approval_consumed=True)
    assert result["status"] == "dry_run"


def test_ati_message_is_blocked_in_read_only_mode():
    client = AtiMessengerClient(Settings(dry_run=False, ati_mode="READ_ONLY"))
    result = client.send_message("dialog-1", "Тест", approval_consumed=True)
    assert result["status"] == "blocked"


def test_approval_is_one_time():
    repository = NegotiationRepository("sqlite:///:memory:")
    message = NegotiationMessage(
        direction=MessageDirection.OUTBOUND,
        text="Тест",
        delivery_status=MessageDeliveryStatus.AWAITING_APPROVAL,
    )
    approval = repository.create_approval("neg-1", message.id)
    repository.approve(approval.id, "operator")
    consumed = repository.consume(approval.id, message.id)
    assert consumed.status.value == "consumed"
    with pytest.raises(ValueError):
        repository.consume(approval.id, message.id)


def test_full_dry_run_negotiation_flow():
    settings = Settings(
        dry_run=True,
        database_url="sqlite:///:memory:",
        anthropic_enabled=False,
    )
    orchestrator = NegotiationOrchestrator(settings)
    session = orchestrator.create_session(
        ati_carrier_id="carrier-1",
        carrier_name="Перевозчик",
        ati_conversation_id="dialog-1",
        route=RouteContext(
            origin="Владивосток",
            destination="Новосибирск",
            cargo="8 автомобилей",
            ready_date="15.07.2026",
        ),
        target_rate=800_000,
        max_rate=900_000,
    )
    prepared = orchestrator.prepare_initial_message(session.id)
    approval_id = prepared["approval"]["id"]
    sent = orchestrator.approve_and_send(approval_id, "operator")
    assert sent["delivery"]["status"] == "dry_run"

    reply = orchestrator.process_inbound_message(
        session.id,
        "Актуально, ставка 850 000 нал, срок 3 дня",
        external_message_id="ati-msg-1",
    )
    assert reply["decision"]["action"] == "counter"
    assert reply["decision"]["proposed_rate"] == 800_000
