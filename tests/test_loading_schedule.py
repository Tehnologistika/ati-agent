from datetime import date

from app.services.loading_schedule import (
    parse_loading_schedule,
)
from app.services.request_parser import (
    parse_transport_request,
)


TODAY = date(2026, 7, 13)


def test_ready_forms_use_universal_text():
    variants = [
        "готов",
        "готова",
        "готово",
        "готовы",
        "авто готово",
        "автомобиль готов",
        "машина готова",
        "лот готов",
        "автомобили готовы",
        "готов к отправке",
        "готова к отправке",
        "готово к отправке",
        "готовы к отправке",
        "готово к погрузке",
        "можно грузить",
        "Готово!",
    ]

    for value in variants:
        schedule = parse_loading_schedule(
            value,
            today=TODAY,
        )

        assert schedule.date_type.value == "ready"

        assert schedule.normalized_text == (
            "Готово к отправке"
        )


def test_today_and_tomorrow():
    today = parse_loading_schedule(
        "сегодня",
        today=TODAY,
    )

    assert today.date_type.value == "ready"
    assert today.normalized_text == (
        "Готово к отправке"
    )

    tomorrow = parse_loading_schedule(
        "завтра",
        today=TODAY,
    )

    assert tomorrow.date_type.value == (
        "from-date"
    )

    assert tomorrow.first_date == date(
        2026,
        7,
        14,
    )

    assert tomorrow.normalized_text == (
        "14 июля 2026"
    )


def test_text_date_and_range():
    single = parse_loading_schedule(
        "15 июля",
        today=TODAY,
    )

    assert single.first_date == date(
        2026,
        7,
        15,
    )

    assert single.normalized_text == (
        "15 июля 2026"
    )

    period = parse_loading_schedule(
        "15–17 июля",
        today=TODAY,
    )

    assert period.first_date == date(
        2026,
        7,
        15,
    )

    assert period.last_date == date(
        2026,
        7,
        17,
    )

    assert period.normalized_text == (
        "15–17 июля 2026"
    )


def test_cross_year_range():
    schedule = parse_loading_schedule(
        "30 декабря - 2 января",
        today=TODAY,
    )

    assert schedule.first_date == date(
        2026,
        12,
        30,
    )

    assert schedule.last_date == date(
        2027,
        1,
        2,
    )


def test_numeric_date_range():
    schedule = parse_loading_schedule(
        "15.07.2026-17.07.2026",
        today=TODAY,
    )

    assert schedule.first_date == date(
        2026,
        7,
        15,
    )

    assert schedule.last_date == date(
        2026,
        7,
        17,
    )


def test_week_permanent_and_rate_request():
    week = parse_loading_schedule(
        "в течение недели",
        today=TODAY,
    )

    assert week.first_date == TODAY
    assert week.last_date == date(
        2026,
        7,
        20,
    )

    permanent = parse_loading_schedule(
        "постоянно",
        today=TODAY,
    )

    assert permanent.date_type.value == (
        "permanent"
    )

    assert permanent.normalized_text == (
        "Постоянная загрузка"
    )

    rate = parse_loading_schedule(
        "запрос ставки",
        today=TODAY,
    )

    assert rate.date_type.value == (
        "rate-request"
    )

    assert rate.normalized_text == (
        "Запрос ставки"
    )


def test_ready_line_is_not_vehicle():
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Владивосток - Москва
        Toyota Camry
        готова
        150 000 наличными
        """
    )

    assert request.vehicle == "Toyota Camry"

    assert request.ready_date == (
        "Готово к отправке"
    )

    assert request.requested_rate == 150_000
    assert request.is_valid_request is True


def test_lot_ready_status():
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Владивосток - Москва
        Лот
        готово к отправке
        1 300 000 наличными
        """
    )

    assert request.is_lot is True

    assert request.ready_date == (
        "Готово к отправке"
    )

    assert request.requested_rate == 1_300_000
    assert request.is_valid_request is True


def test_labeled_period_and_rate():
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

    assert request.ready_date == (
        "15–17 июля 2030"
    )

    assert request.vehicle == "Toyota Camry"
    assert request.requested_rate == 100_000
    assert request.payment_type == "без НДС"
    assert request.is_valid_request is True
