from app.data_models.negotiation import (
    MessagePurpose,
    NegotiationAction,
    NegotiationDecision,
    NegotiationSession,
)
from app.services.rate_parser import analyze_carrier_reply


def _round_to_thousand(amount: float) -> int:
    return max(1_000, int(round(amount / 1_000.0) * 1_000))


class NegotiationPolicy:
    """Deterministic negotiation policy. It proposes actions but never sends them."""

    def initial_decision(self) -> NegotiationDecision:
        return NegotiationDecision(
            action=NegotiationAction.REQUEST_INITIAL_RATE,
            purpose=MessagePurpose.INITIAL_RATE_REQUEST,
            reason="Request availability, all-in rate and key conditions.",
        )

    def decide(self, session: NegotiationSession, reply_text: str) -> NegotiationDecision:
        analysis = analyze_carrier_reply(reply_text)

        if analysis.availability is False:
            return NegotiationDecision(
                action=NegotiationAction.CLOSE_UNAVAILABLE,
                purpose=MessagePurpose.CLOSE,
                reason="Carrier explicitly reported that the vehicle or route is unavailable.",
                requires_approval=True,
            )

        offer = analysis.offer
        if offer is None:
            return NegotiationDecision(
                action=NegotiationAction.ASK_RATE,
                purpose=MessagePurpose.ASK_RATE,
                reason="No unambiguous rate was found in the carrier reply.",
            )

        if session.max_rate is not None and offer.amount > session.max_rate:
            proposed = session.target_rate or session.max_rate
            proposed = min(proposed, session.max_rate)
            return NegotiationDecision(
                action=NegotiationAction.COUNTER,
                purpose=MessagePurpose.COUNTEROFFER,
                reason="Carrier rate exceeds the maximum permitted rate.",
                proposed_rate=_round_to_thousand(proposed),
                offer=offer,
            )

        if session.target_rate is not None and offer.amount > session.target_rate:
            if offer.amount <= int(session.target_rate * 1.15):
                proposed = session.target_rate
            else:
                proposed = max(session.target_rate, _round_to_thousand(offer.amount * 0.93))
            if session.max_rate is not None:
                proposed = min(proposed, session.max_rate)
            return NegotiationDecision(
                action=NegotiationAction.COUNTER,
                purpose=MessagePurpose.COUNTEROFFER,
                reason="Carrier rate is workable but above the target rate.",
                proposed_rate=_round_to_thousand(proposed),
                offer=offer,
            )

        return NegotiationDecision(
            action=NegotiationAction.PROPOSE_ACCEPTANCE,
            purpose=MessagePurpose.PROPOSE_ACCEPTANCE,
            reason="Carrier rate is at or below the target or no internal threshold was set.",
            proposed_rate=offer.amount,
            offer=offer,
        )
