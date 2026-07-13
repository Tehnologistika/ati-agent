from app.services.request_parser import (
    parse_transport_request,
)


def test_labeled_rate_is_parsed():
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

    assert request.requested_rate == 100_000
    assert request.payment_type == "без НДС"
    assert request.vehicle == "Toyota Camry"
    assert request.is_valid_request is True


def test_labeled_price_is_parsed():
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Владивосток - Москва
        Toyota Camry
        Цена: 150 000
        """
    )

    assert request.requested_rate == 150_000
    assert request.vehicle == "Toyota Camry"


def test_labeled_cost_with_dash_is_parsed():
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Владивосток - Новосибирск
        Лот
        Стоимость - 850 000
        """
    )

    assert request.requested_rate == 850_000
    assert request.is_lot is True


def test_bare_rate_still_works():
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Владивосток - Москва
        Toyota Camry
        150 000
        """
    )

    assert request.requested_rate == 150_000


def test_date_range_is_not_mistaken_for_rate():
    request = parse_transport_request(
        """
        #ЗАЯВКА
        Маршрут: Москва - Казань
        Авто: Toyota Camry
        Готовность: 15-17 июля 2030
        """
    )

    assert request.requested_rate is None
