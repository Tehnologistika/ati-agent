from app.services.draft_builder import (
    build_ati_draft,
)
from app.services.request_parser import (
    parse_transport_request,
)


def test_vladivostok_novosibirsk_freeform():
    text = """
#ЗАЯВКА

Владивосток- Новосибирск

8 авто

900 000 наличными
"""

    result = parse_transport_request(text)

    assert result.is_valid_request is True
    assert result.origin == "Владивосток"
    assert result.destination == "Новосибирск"

    assert result.route_points == [
        "Владивосток",
        "Новосибирск",
    ]

    assert result.vehicle == "8 авто"
    assert result.requested_rate == 900_000
    assert result.payment_type == "наличными"


def test_multistop_moscow_mineralnye_vody():
    text = """
#заявка

Москва (2 погрузки) - Ростов- Мин. Воды

2 джеттура т2
1 джеттур x70
4 джеттура дашинг

220 000 с НДС
"""

    result = parse_transport_request(text)

    assert result.is_valid_request is True

    assert result.origin == "Москва"
    assert (
        result.destination
        == "Минеральные Воды"
    )

    assert result.route_points == [
        "Москва",
        "Ростов",
        "Минеральные Воды",
    ]

    assert result.vehicle == (
        "2 джеттура т2\n"
        "1 джеттур x70\n"
        "4 джеттура дашинг"
    )

    assert result.requested_rate == 220_000
    assert result.payment_type == "с НДС"


def test_multistop_route_to_adygea():
    text = """
#заявка

Москва (1 погрузка) - Ростов - Адыгея

3 джеттура x70
1 джеттур т2
2 джеттура т1

210 000 с НДС
"""

    result = parse_transport_request(text)

    assert result.is_valid_request is True

    assert result.route_points == [
        "Москва",
        "Ростов",
        "Адыгея",
    ]

    assert result.origin == "Москва"
    assert result.destination == "Адыгея"
    assert result.requested_rate == 210_000


def test_hyphenated_city_is_not_split():
    text = """
#ЗАЯВКА

Ростов-на-Дону - Москва

Toyota Camry

150 000 без НДС
"""

    result = parse_transport_request(text)

    assert result.is_valid_request is True

    assert result.route_points == [
        "Ростов-на-Дону",
        "Москва",
    ]


def test_draft_preserves_intermediate_points():
    text = """
#ЗАЯВКА

Москва - Ростов - Мин. Воды

Toyota Camry

180 000 наличными
"""

    request = parse_transport_request(text)
    draft = build_ati_draft(request)

    assert draft.route == (
        "Москва — Ростов — Минеральные Воды"
    )

    assert draft.route_points == [
        "Москва",
        "Ростов",
        "Минеральные Воды",
    ]

    assert draft.requested_rate == 180_000
