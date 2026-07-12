from app.services.publication_max import (
    build_missing_fields_message,
    build_publication_card,
    is_publication_request,
    parse_publication_callback,
    publication_buttons,
)


def test_publication_request_marker():
    assert is_publication_request(
        "#ЗАЯВКА\nМаршрут: Москва — Казань"
    )
    assert is_publication_request(
        "Новая #заявка на перевозку"
    )
    assert not is_publication_request(
        "Маршрут: Москва — Казань"
    )


def test_publication_callback_parser():
    assert parse_publication_callback(
        "publication:approve:publication-123"
    ) == (
        "approve",
        "publication-123",
    )

    assert parse_publication_callback(
        "publication:reject:publication-456"
    ) == (
        "reject",
        "publication-456",
    )

    assert parse_publication_callback(
        "ati:approve:approval-1"
    ) is None


def test_publication_buttons():
    buttons = publication_buttons(
        "publication-777"
    )

    assert buttons[0][0]["payload"] == (
        "publication:approve:publication-777"
    )
    assert buttons[0][1]["payload"] == (
        "publication:reject:publication-777"
    )


def test_missing_fields_message():
    text = build_missing_fields_message(
        [
            "origin",
            "destination",
            "vehicle",
        ],
        author_name="Тимур",
    )

    assert "Тимур" in text
    assert "город загрузки" in text
    assert "город выгрузки" in text
    assert "автомобиль или груз" in text


def test_publication_card():
    text = build_publication_card(
        {
            "origin": "Владивосток",
            "destination": "Москва",
            "vehicle": "Toyota Camry",
            "ready_date": "15 июля",
            "vehicle_condition": "На ходу",
            "payment_type": "Наличные",
            "comment": "Тест",
        },
        {
            "title": (
                "Перевозка авто | "
                "Владивосток — Москва"
            ),
            "route": "Владивосток — Москва",
            "cargo_description": "Toyota Camry",
            "ready_date": "15 июля",
            "payment_type": "Наличные",
            "comment": "Тест",
            "dry_run": True,
        },
        "publication-123",
    )

    assert "ЧЕРНОВИК ПУБЛИКАЦИИ" in text
    assert "Toyota Camry" in text
    assert "DRY_RUN" in text
    assert "publication-123" in text
