import requests

from app.data_models.negotiation import (
    NegotiationAction,
    NegotiationDecision,
    NegotiationSession,
)
from app.integrations.anthropic_client import AnthropicClient


SYSTEM_PROMPT = """Вы ведёте деловую переписку от имени ООО «ТехноЛогистика» с перевозчиком на ATI.su.
Цель — получить актуальную окончательную ставку, дату загрузки, форму оплаты, срок доставки и существенные условия, затем добиться разумного снижения цены и подготовить договорённость.
Правила:
1. Обращайтесь на «Вы», пишите коротко, уверенно и доброжелательно.
2. Не раскрывайте внутреннюю целевую ставку, максимальный бюджет, маржу и внутренние комментарии, кроме конкретной встречной ставки, которую разрешено назвать.
3. Не придумывайте факты и не меняйте маршрут, груз, дату или условия.
4. Не подтверждайте окончательно перевозку, договор, бронь или оплату. Формулируйте, что окончательное закрепление будет после внутреннего подтверждения.
5. Не используйте давление, массовую рассылку, стрелки маршрута, канцелярит и упоминание искусственного интеллекта.
6. Верните только готовый текст одного сообщения без пояснений и кавычек.
"""


def _money(amount: int | None) -> str:
    if amount is None:
        return ""
    return f"{amount:,}".replace(",", " ") + " ₽"


def _route(session: NegotiationSession) -> str:
    return f"{session.route.origin} — {session.route.destination}"


def _fallback(session: NegotiationSession, decision: NegotiationDecision) -> str:
    route = _route(session)
    cargo = session.route.cargo
    date = session.route.ready_date or "по согласованию"

    if decision.action == NegotiationAction.REQUEST_INITIAL_RATE:
        return (
            f"Здравствуйте. Подскажите, пожалуйста, актуальна ли у Вас машина по направлению {route}? "
            f"Нужно перевезти: {cargo}. Готовность: {date}. "
            "Какая у Вас окончательная ставка за рейс, ближайшая дата загрузки, форма оплаты и срок доставки?"
        )

    if decision.action == NegotiationAction.ASK_RATE:
        return (
            "Спасибо за ответ. Уточните, пожалуйста, Вашу окончательную ставку за рейс, "
            "форму оплаты, ближайшую дату загрузки и ориентировочный срок доставки."
        )

    if decision.action == NegotiationAction.COUNTER:
        return (
            f"Спасибо. По этому направлению можем рассмотреть {_money(decision.proposed_rate)} за рейс. "
            "Сможете подтвердить эту ставку? Также уточните, пожалуйста, дату загрузки, форму оплаты и срок доставки."
        )

    if decision.action == NegotiationAction.PROPOSE_ACCEPTANCE:
        return (
            f"Ставка {_money(decision.proposed_rate)} предварительно подходит. "
            "Подтвердите, пожалуйста, ближайшую дату загрузки, форму оплаты, срок доставки и что дополнительных расходов по рейсу не будет. "
            "После внутреннего согласования закрепим перевозку."
        )

    if decision.action == NegotiationAction.CLOSE_UNAVAILABLE:
        return "Понял, спасибо за ответ. Будем иметь Вас в виду по следующим перевозкам."

    return "Спасибо. Уточните, пожалуйста, актуальные условия по этой перевозке."


class NegotiationMessageBuilder:
    def __init__(self, anthropic: AnthropicClient):
        self.anthropic = anthropic

    def build(
        self,
        session: NegotiationSession,
        decision: NegotiationDecision,
        inbound_text: str | None = None,
    ) -> str:
        fallback = _fallback(session, decision)
        prompt = (
            f"Маршрут: {_route(session)}\n"
            f"Груз: {session.route.cargo}\n"
            f"Готовность: {session.route.ready_date or 'по согласованию'}\n"
            f"Действие: {decision.action.value}\n"
            f"Разрешённая встречная ставка: {_money(decision.proposed_rate) or 'не указана'}\n"
            f"Последний ответ перевозчика: {inbound_text or 'переписка ещё не началась'}\n"
            f"Безопасный шаблон: {fallback}\n"
            "Подготовьте улучшенный вариант, сохранив все ограничения."
        )
        try:
            generated = self.anthropic.generate(SYSTEM_PROMPT, prompt)
        except (requests.RequestException, ValueError, KeyError):
            generated = None

        text = (generated or fallback).strip().strip('"')
        if not text or len(text) > 1_500:
            return fallback
        return text
