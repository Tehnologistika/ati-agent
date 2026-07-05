from app.data_models.request import AtiDraft, TransportRequest


def build_ati_draft(request: TransportRequest, dry_run: bool = True) -> AtiDraft:
    """Build a safe ATI publication draft from a parsed request."""

    route = None
    if request.origin and request.destination:
        route = f"{request.origin} — {request.destination}"

    title_parts = ["Перевозка авто"]
    if route:
        title_parts.append(route)
    title = " | ".join(title_parts)

    return AtiDraft(
        title=title,
        route=route,
        cargo_description=request.vehicle,
        ready_date=request.ready_date,
        payment_type=request.payment_type,
        comment=request.comment,
        dry_run=dry_run,
    )
