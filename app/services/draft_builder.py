from app.data_models.request import (
    AtiDraft,
    TransportRequest,
)


def build_ati_draft(
    request: TransportRequest,
    dry_run: bool = True,
) -> AtiDraft:
    """
    Build a safe ATI publication draft from
    a parsed transport request.
    """

    route_points = list(
        request.route_points
    )

    if (
        not route_points
        and request.origin
        and request.destination
    ):
        route_points = [
            request.origin,
            request.destination,
        ]

    route = (
        " — ".join(route_points)
        if route_points
        else None
    )

    title_parts = [
        (
            "Лот автомобилей (полный автовоз)"
            if request.is_lot
            else "Перевозка авто"
        ),
    ]

    if route:
        title_parts.append(route)

    title = " | ".join(title_parts)

    return AtiDraft(
        title=title,
        route=route,
        route_points=route_points,
        is_lot=request.is_lot,
        cargo_description=request.vehicle,
        ready_date=request.ready_date,
        requested_rate=request.requested_rate,
        currency=request.currency,
        payment_type=request.payment_type,
        comment=request.comment,
        dry_run=dry_run,
    )
