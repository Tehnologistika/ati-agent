from app.services.request_parser import parse_transport_request


def test_parse_sample_request():
    text = """ЗАЯВКА

Маршрут: Владивосток — Москва
Авто: Toyota Camry 2021
На ходу: да
Дата готовности: 10 июля
Оплата: безнал без НДС
Комментарий: клиент хочет ближайшее место
"""
    result = parse_transport_request(text)

    assert result.is_valid_request is True
    assert result.origin == "Владивосток"
    assert result.destination == "Москва"
    assert result.vehicle == "Toyota Camry 2021"
    assert result.payment_type == "безнал без НДС"
