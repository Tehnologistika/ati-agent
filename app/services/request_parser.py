import re

from app.data_models.request import TransportRequest


def _extract_after_label(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = rf"(?:^|\n)\s*{re.escape(label)}\s*[:\-]\s*(.+)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_route(text: str) -> tuple[str | None, str | None]:
    route = _extract_after_label(text, ["Маршрут", "Направление"])
    if route:
        parts = re.split(r"\s*(?:—|–|->|→|-)\s*", route, maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

    origin = _extract_after_label(text, ["Откуда", "Загрузка", "Город загрузки"])
    destination = _extract_after_label(text, ["Куда", "Выгрузка", "Город выгрузки"])
    return origin, destination


def parse_transport_request(raw_text: str, source: str = "manual") -> TransportRequest:
    """Parse a transport request from free text.

    MVP parser: deterministic and conservative. It only extracts clear fields and never
    sends or publishes anything.
    """

    origin, destination = _extract_route(raw_text)
    vehicle = _extract_after_label(raw_text, ["Авто", "Автомобиль", "Груз", "Машина"])
    ready_date = _extract_after_label(raw_text, ["Дата готовности", "Дата", "Готовность"])
    condition = _extract_after_label(raw_text, ["На ходу", "Состояние"])
    payment = _extract_after_label(raw_text, ["Оплата", "Форма оплаты"])
    comment = _extract_after_label(raw_text, ["Комментарий", "Примечание"])

    request = TransportRequest(
        source=source,
        raw_text=raw_text,
        origin=origin,
        destination=destination,
        vehicle=vehicle,
        ready_date=ready_date,
        vehicle_condition=condition,
        payment_type=payment,
        comment=comment,
        is_valid_request="заявка" in raw_text.lower(),
    )

    required = {
        "origin": request.origin,
        "destination": request.destination,
        "vehicle": request.vehicle,
    }
    request.missing_fields = [name for name, value in required.items() if not value]
    if request.missing_fields:
        request.is_valid_request = False

    return request
