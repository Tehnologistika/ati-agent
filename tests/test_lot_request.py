from app.services.draft_builder import (
    build_ati_draft,
)
from app.services.publication_max import (
    build_publication_card,
)
from app.services.request_parser import (
    LOT_CARGO_DESCRIPTION,
    parse_transport_request,
)


def test_freeform_lot_is_complete_request():
    text = """
#ЗАЯВКА

Владивосток - Москва

Лот

1 300 000 наличными
"""

    request = parse_transport_request(text)

    assert request.is_valid_request is True
    assert request.is_lot is True

    assert request.origin == "Владивосток"
    assert request.destination == "Москва"

    assert request.vehicle == (
        LOT_CARGO_DESCRIPTION
    )

    assert request.requested_rate == 1_300_000
    assert request.payment_type == "наличными"
    assert request.missing_fields == []


def test_labeled_lot_is_supported():
    text = """
#ЗАЯВКА
Маршрут: Москва - Краснодар
Груз: Лот
Оплата: безнал с НДС
"""

    request = parse_transport_request(text)

    assert request.is_valid_request is True
    assert request.is_lot is True
    assert request.vehicle == (
        LOT_CARGO_DESCRIPTION
    )
    assert request.payment_type == (
        "безнал с НДС"
    )


def test_lot_builds_full_carrier_draft():
    text = """
#ЗАЯВКА

Москва - Ростов - Адыгея

ЛОТ

210 000 с НДС
"""

    request = parse_transport_request(text)
    draft = build_ati_draft(request)

    assert draft.is_lot is True

    assert draft.title == (
        "Лот автомобилей (полный автовоз) | "
        "Москва — Ростов — Адыгея"
    )

    assert draft.route_points == [
        "Москва",
        "Ростов",
        "Адыгея",
    ]

    assert draft.cargo_description == (
        LOT_CARGO_DESCRIPTION
    )


def test_lot_card_clearly_marks_full_carrier():
    text = """
#ЗАЯВКА

Владивосток - Новосибирск

Лот

900 000 наличными
"""

    request = parse_transport_request(text)
    draft = build_ati_draft(request)

    card = build_publication_card(
        request.model_dump(),
        draft.model_dump(),
        "publication-lot-test",
    )

    assert "Лот — полный автовоз" in card

    assert (
        "Владивосток — Новосибирск"
        in card
    )

    assert LOT_CARGO_DESCRIPTION in card


def test_similar_word_does_not_enable_lot():
    text = """
#ЗАЯВКА

Москва - Казань

Авто: Lotus Emira
Комментарий: положить документы в лоток
"""

    request = parse_transport_request(text)

    assert request.is_valid_request is True
    assert request.is_lot is False
    assert request.vehicle == "Lotus Emira"


def test_no_vehicle_and_no_lot_is_incomplete():
    text = """
#ЗАЯВКА

Москва - Казань

150 000 наличными
"""

    request = parse_transport_request(text)

    assert request.is_valid_request is False
    assert request.is_lot is False
    assert "vehicle" in request.missing_fields
