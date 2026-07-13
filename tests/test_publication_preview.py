import pytest

from app.config import Settings
from app.data_models.publication import (
    PublicationApprovalStatus,
)
from app.publication_orchestrator import (
    PublicationOrchestrator,
)
from app.services.draft_builder import (
    build_ati_draft,
)
from app.services.publication_max import (
    build_publication_card,
    publication_buttons,
)
from app.services.publication_preview import (
    build_publication_preview,
)
from app.services.request_parser import (
    parse_transport_request,
)


LOT_REQUEST = """
#ЗАЯВКА

Владивосток - Москва

Лот

1 300 000 наличными
""".strip()


def settings_for_test(
    tmp_path,
    *,
    dry_run=True,
):
    return Settings(
        _env_file=None,
        dry_run=dry_run,
        ati_mode=(
            "READ_ONLY"
            if dry_run
            else "APPROVAL_REQUIRED"
        ),
        ati_contact_id="7776989",
        max_enabled=True,
        max_owner_user_id="137319351",
        database_url=(
            "sqlite:///"
            + str(tmp_path / "preview.db")
        ),
        events_log_path=str(
            tmp_path / "events.jsonl"
        ),
    )


def test_preview_builds_exact_lot_note(
    tmp_path,
):
    request = parse_transport_request(
        LOT_REQUEST
    )

    preview = build_publication_preview(
        request,
        "publication-test",
        settings_for_test(tmp_path),
    )

    assert preview.profile.value == (
        "full_carrier_lot"
    )

    assert preview.ready_for_api is False

    assert (
        "Требуется один полный автовоз"
        in preview.note
    )

    assert (
        "полезную площадь"
        in preview.note
    )

    assert (
        "Владивосток — Москва"
        in preview.note
    )

    assert "contact_ids" not in (
        preview.missing_fields
    )

    assert "board_ids" in (
        preview.missing_fields
    )

    assert "body_type_ids" in (
        preview.missing_fields
    )

    assert "currency_type_id" in (
        preview.missing_fields
    )

    assert "loading_date_type" in (
        preview.missing_fields
    )

    assert "weight_confirmation" in (
        preview.missing_fields
    )

    assert (
        "resolved_route[0].city_id"
        in preview.missing_fields
    )

    assert (
        "resolved_route[1].city_id"
        in preview.missing_fields
    )


def test_card_contains_exact_ati_preview(
    tmp_path,
):
    request = parse_transport_request(
        LOT_REQUEST
    )

    draft = build_ati_draft(
        request,
        dry_run=True,
    )

    preview = build_publication_preview(
        request,
        "publication-card",
        settings_for_test(tmp_path),
    )

    card = build_publication_card(
        request.model_dump(),
        draft.model_dump(),
        "publication-card",
        ati_preview=preview.model_dump(
            mode="json"
        ),
    )

    assert "ТРЕБУЕТ НАСТРОЙКИ" in card
    assert "Лот — полный автовоз" in card

    assert (
        "Полный автовоз (FTL)"
        in card
    )

    assert (
        "Количество авто:** "
        "подбирается под вместимость автовоза"
        in card
    )

    assert (
        "Требуется один полный автовоз"
        in card
    )

    assert (
        "Подтвердить населённый пункт"
        in card
    )

    assert (
        "Реальная публикация заблокирована"
        in card
    )


def test_buttons_respect_readiness():
    ready = publication_buttons(
        "publication-ready",
        ready_for_api=True,
        dry_run=False,
    )

    assert ready[0][0]["text"] == (
        "Опубликовать"
    )

    preview = publication_buttons(
        "publication-preview",
        ready_for_api=False,
        dry_run=True,
    )

    assert preview[0][0]["text"] == (
        "Проверить DRY_RUN"
    )

    blocked = publication_buttons(
        "publication-blocked",
        ready_for_api=False,
        dry_run=False,
    )

    assert len(blocked[0]) == 1
    assert blocked[0][0]["text"] == (
        "Отклонить"
    )


def test_orchestrator_returns_preview(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    result = orchestrator.prepare_from_text(
        LOT_REQUEST,
        source="max:test",
        source_chat_id="100",
        source_message_id="message-1",
        requested_by="200",
    )

    assert result["approval"] is not None
    assert result["ati_preview"] is not None

    assert result["ati_preview"][
        "profile"
    ] == "full_carrier_lot"

    assert result["ati_preview"][
        "ready_for_api"
    ] is False


def test_real_mode_blocks_incomplete_payload(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(
            tmp_path,
            dry_run=False,
        )
    )

    prepared = orchestrator.prepare_from_text(
        LOT_REQUEST,
        source="max:test",
        source_chat_id="100",
        source_message_id="message-2",
        requested_by="200",
    )

    approval_id = prepared["approval"]["id"]

    with pytest.raises(
        RuntimeError,
        match="Публикация заблокирована",
    ):
        orchestrator.approve_and_publish(
            approval_id,
            "137319351",
        )

    stored = orchestrator.repository.get(
        approval_id
    )

    assert stored.status == (
        PublicationApprovalStatus.PENDING
    )


def test_dry_run_button_cycle_still_works(
    tmp_path,
):
    orchestrator = PublicationOrchestrator(
        settings_for_test(tmp_path)
    )

    prepared = orchestrator.prepare_from_text(
        LOT_REQUEST,
        source="max:test",
        source_chat_id="100",
        source_message_id="message-3",
        requested_by="200",
    )

    approval_id = prepared["approval"]["id"]

    result = orchestrator.approve_and_publish(
        approval_id,
        "137319351",
    )

    assert result["publication_result"][
        "status"
    ] == "dry_run"

    assert result["ati_preview"][
        "profile"
    ] == "full_carrier_lot"
