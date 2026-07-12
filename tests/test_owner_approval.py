import pytest

from app.config import Settings
from app.data_models.negotiation import RouteContext
from app.negotiation_orchestrator import NegotiationOrchestrator


def _orchestrator(owner_id: str = "777") -> NegotiationOrchestrator:
    return NegotiationOrchestrator(
        Settings(
            dry_run=True,
            max_enabled=True,
            max_owner_user_id=owner_id,
            database_url="sqlite:///:memory:",
            anthropic_enabled=False,
        )
    )


def _prepared(orchestrator: NegotiationOrchestrator):
    session = orchestrator.create_session(
        ati_carrier_id="123456",
        carrier_name="Тестовый перевозчик",
        ati_conversation_id=None,
        route=RouteContext(
            origin="Москва",
            destination="Владивосток",
            cargo="автомобили",
        ),
    )
    return orchestrator.prepare_initial_message(session.id)


def test_non_owner_cannot_approve_ati_message():
    orchestrator = _orchestrator(owner_id="777")
    prepared = _prepared(orchestrator)

    with pytest.raises(PermissionError):
        orchestrator.approve_and_send(prepared["approval"]["id"], "123")


def test_owner_can_approve_and_dry_run_creates_synthetic_dialog():
    orchestrator = _orchestrator(owner_id="777")
    prepared = _prepared(orchestrator)

    result = orchestrator.approve_and_send(prepared["approval"]["id"], "777")

    assert result["dialog_creation"]["status"] == "dry_run"
    assert result["delivery"]["status"] == "dry_run"
    assert result["delivery"]["conversation_id"] == "dry-run:123456.0"


def test_missing_owner_id_blocks_approvals_when_max_is_enabled():
    orchestrator = NegotiationOrchestrator(
        Settings(
            dry_run=True,
            max_enabled=True,
            max_owner_user_id=None,
            database_url="sqlite:///:memory:",
        )
    )
    prepared = _prepared(orchestrator)

    with pytest.raises(RuntimeError):
        orchestrator.approve_and_send(prepared["approval"]["id"], "777")
