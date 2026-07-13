from app.config import Settings
from app.services.draft_builder import (
    build_ati_draft,
)
from app.services.publication_max import (
    build_publication_card,
)
from app.services.publication_preview import (
    build_publication_preview,
)
from app.services.request_parser import (
    parse_transport_request,
)


def settings_for_test(tmp_path):
    return Settings(
        _env_file=None,
        dry_run=True,
        ati_mode="READ_ONLY",
        ati_contact_id="7776989",
        max_enabled=True,
        max_owner_user_id="137319351",
        database_url=(
            "sqlite:///"
            + str(tmp_path / "dates.db")
        ),
        events_log_path=str(
            tmp_path / "events.jsonl"
        ),
    )


def make_card(
    request,
    preview,
):
    draft = build_ati_draft(
        request,
        dry_run=True,
    )

    return build_publication_card(
        request.model_dump(),
        draft.model_dump(),
        "publication-date-test",
        ati_preview=preview.model_dump(
            mode="json"
        ),
    )


def test_ready_status_reaches_ati_and_max(
    tmp_path,
):
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Владивосток - Москва
        Лот
        готова
        1 300 000 наличными
        """
    )

    preview = build_publication_preview(
        request,
        "publication-ready-test",
        settings_for_test(tmp_path),
    )

    dates = (
        preview.payload[
            "cargo_application"
        ]["route"]["loading"]["dates"]
    )

    card = make_card(
        request,
        preview,
    )

    assert request.ready_date == (
        "Готово к отправке"
    )

    assert dates == {
        "type": "ready",
    }

    assert "loading_date_type" not in (
        preview.missing_fields
    )

    assert "Готово к отправке." in (
        preview.note
    )

    assert (
        "**Готовность к отправке:** "
        "Готово к отправке"
        in card
    )


def test_exact_period_reaches_ati_json(
    tmp_path,
):
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Маршрут: Москва - Казань
        Авто: Toyota Camry
        Готовность: 15-17 июля 2030
        Ставка: 100 000
        Оплата: без НДС
        """
    )

    preview = build_publication_preview(
        request,
        "publication-period-test",
        settings_for_test(tmp_path),
    )

    dates = (
        preview.payload[
            "cargo_application"
        ]["route"]["loading"]["dates"]
    )

    card = make_card(
        request,
        preview,
    )

    assert dates == {
        "type": "from-date",
        "first_date": "2030-07-15",
        "last_date": "2030-07-17",
    }

    assert (
        "Pериод готовности"
        not in preview.note
    )

    assert (
        "Период готовности к отправке: "
        "15–17 июля 2030 г."
        in preview.note
    )

    assert (
        "**Готовность к отправке:** "
        "15–17 июля 2030"
        in card
    )


def test_permanent_loading_reaches_ati(
    tmp_path,
):
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Владивосток - Москва
        Лот
        постоянно
        1 300 000 наличными
        """
    )

    preview = build_publication_preview(
        request,
        "publication-permanent-test",
        settings_for_test(tmp_path),
    )

    dates = (
        preview.payload[
            "cargo_application"
        ]["route"]["loading"]["dates"]
    )

    card = make_card(
        request,
        preview,
    )

    assert dates == {
        "type": "permanent",
        "periodicity": "everyday",
    }

    assert (
        "Загрузка выполняется постоянно."
        in preview.note
    )

    assert (
        "**Готовность к отправке:** "
        "Постоянная загрузка"
        in card
    )


def test_missing_date_remains_blocked(
    tmp_path,
):
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Владивосток - Москва
        Лот
        1 300 000 наличными
        """
    )

    preview = build_publication_preview(
        request,
        "publication-missing-date-test",
        settings_for_test(tmp_path),
    )

    card = make_card(
        request,
        preview,
    )

    assert "loading_date_type" in (
        preview.missing_fields
    )

    assert (
        "**Готовность к отправке:** "
        "не указано"
        in card
    )
