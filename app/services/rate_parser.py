import re
from decimal import Decimal, InvalidOperation

from app.data_models.negotiation import CarrierReplyAnalysis, RateOffer


_UNAVAILABLE_PATTERNS = (
    r"\bнеактуальн",
    r"\bнет\s+(?:машины|места|возможности)",
    r"\bне\s+поед",
    r"\bзанят",
    r"\bуже\s+(?:загрузил|загружен|закрыл)",
)

_AVAILABLE_PATTERNS = (
    r"\bактуальн",
    r"\bесть\s+(?:машина|место)",
    r"\bготов\s+(?:взять|поехать|загрузиться)",
    r"\bможем\s+(?:взять|забрать|поехать)",
)

_UNIT_PATTERN = (
    r"млн(?:\.|\s*руб(?:лей|ля)?)?|миллион(?:а|ов)?|"
    r"тыс(?:\.|яч[аи]?)?|т\.?\s*р\.?|"
    r"руб(?:\.|лей|ля)?|₽|usd|доллар(?:а|ов)?|\$|eur|евро|€"
)

_AMOUNT_WITH_UNIT = re.compile(
    rf"(?P<amount>\d+(?:[\s\u00a0]\d{{3}})*(?:[.,]\d+)?)\s*(?P<unit>{_UNIT_PATTERN})",
    re.IGNORECASE,
)

_SPACED_AMOUNT = re.compile(r"(?<!\d)(?P<amount>\d{1,3}(?:[\s\u00a0]\d{3})+)(?!\d)")
_KEYWORD_AMOUNT = re.compile(
    r"(?:ставк[аиу]|цен[аеу]|за\s+рейс|готовы?\s+за|поедем\s+за)\D{0,12}"
    r"(?P<amount>\d{4,7})(?!\d)",
    re.IGNORECASE,
)


def _availability(text: str) -> bool | None:
    lowered = text.lower()
    if any(re.search(pattern, lowered) for pattern in _UNAVAILABLE_PATTERNS):
        return False
    if any(re.search(pattern, lowered) for pattern in _AVAILABLE_PATTERNS):
        return True
    return None


def _parse_decimal(raw: str) -> Decimal | None:
    normalized = raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _currency(unit: str, text: str) -> str:
    value = f"{unit} {text}".lower()
    if any(token in value for token in ("usd", "$", "доллар")):
        return "USD"
    if any(token in value for token in ("eur", "€", "евро")):
        return "EUR"
    return "RUB"


def _multiplier(unit: str) -> int:
    lowered = unit.lower().replace(" ", "")
    if lowered.startswith("млн") or lowered.startswith("миллион"):
        return 1_000_000
    if lowered.startswith("тыс") or lowered.startswith("т.") or lowered.startswith("тр"):
        return 1_000
    return 1


def _extract_amount(text: str) -> tuple[int, str, float] | None:
    candidates: list[tuple[int, str, float]] = []

    for match in _AMOUNT_WITH_UNIT.finditer(text):
        number = _parse_decimal(match.group("amount"))
        if number is None:
            continue
        unit = match.group("unit")
        amount = int(number * _multiplier(unit))
        if amount >= 1_000:
            candidates.append((amount, _currency(unit, text), 0.98))

    for match in _SPACED_AMOUNT.finditer(text):
        number = _parse_decimal(match.group("amount"))
        if number is not None and number >= 10_000:
            candidates.append((int(number), _currency("", text), 0.90))

    for match in _KEYWORD_AMOUNT.finditer(text):
        number = _parse_decimal(match.group("amount"))
        if number is not None and number >= 5_000:
            candidates.append((int(number), _currency("", text), 0.82))

    if not candidates:
        return None

    return max(candidates, key=lambda item: item[2])


def _extract_vat_mode(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"без\s+ндс", lowered):
        return "without_vat"
    if re.search(r"(?:с|включая)\s+ндс", lowered):
        return "with_vat"
    return None


def _extract_payment_type(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"\bнал(?:ичк[а-я]*)?\b", lowered):
        return "cash"
    if re.search(r"\bбезнал(?:ичн[а-я]*)?\b", lowered):
        return "cashless"
    return None


def _extract_transit_days(text: str) -> int | None:
    match = re.search(r"\b(\d{1,2})\s*(?:дн(?:я|ей)?|сут(?:ок|ки)?)\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _extract_loading_date(text: str) -> str | None:
    match = re.search(r"\b(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)\b", text)
    return match.group(1) if match else None


def analyze_carrier_reply(text: str) -> CarrierReplyAnalysis:
    """Extract availability, rate and basic transport conditions from a carrier reply."""

    amount_data = _extract_amount(text)
    offer = None
    if amount_data:
        amount, currency, confidence = amount_data
        offer = RateOffer(
            amount=amount,
            currency=currency,
            vat_mode=_extract_vat_mode(text),
            payment_type=_extract_payment_type(text),
            transit_days=_extract_transit_days(text),
            loading_date=_extract_loading_date(text),
            raw_text=text,
            confidence=confidence,
        )

    availability = _availability(text)
    return CarrierReplyAnalysis(
        availability=availability,
        offer=offer,
        needs_clarification=availability is not False and offer is None,
        raw_text=text,
    )
