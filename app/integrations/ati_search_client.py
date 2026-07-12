from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from app.config import Settings


class AtiSearchClient:
    """Read-only client for ATI geo lookup and carrier search services."""

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.settings.ati_api_base_url.rstrip('/')}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.ati_access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _configuration_error(self) -> dict[str, Any] | None:
        if self.settings.ati_access_token:
            return None
        return {
            "status": "configuration_required",
            "message": "ATI_ACCESS_TOKEN is not configured",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        max_retries = max(0, self.settings.ati_http_max_retries)
        for attempt in range(max_retries + 1):
            try:
                response = self.session.request(
                    method,
                    self._url(path),
                    timeout=self.settings.ati_http_timeout_seconds,
                    allow_redirects=True,
                    **kwargs,
                )
            except requests.RequestException:
                if attempt >= max_retries:
                    raise
                time.sleep(0.1 * (2**attempt))
                continue

            if response.status_code != 429 or attempt >= max_retries:
                response.raise_for_status()
                return response

            time.sleep(0.1 * (2**attempt))

        raise RuntimeError("ATI request retry loop exited unexpectedly")

    def resolve_city(self, city_name: str, *, limit: int = 10) -> dict[str, Any]:
        """Resolve a free-form city name to an ATI city identifier."""

        error = self._configuration_error()
        if error:
            return error

        response = self._request(
            "POST",
            self.settings.ati_geo_autocomplete_path,
            headers=self._headers(),
            json={
                "prefix": city_name,
                "suggestion_types": 1,
                "limit": min(max(limit, 1), 50),
                "country_id": self.settings.ati_default_country_id,
            },
        )
        data = response.json()
        suggestions = data.get("suggestions") or []
        city_suggestions = [item for item in suggestions if item.get("city")]

        normalized = city_name.strip().casefold()
        exact = next(
            (
                item
                for item in city_suggestions
                if str(item.get("city", {}).get("name", "")).strip().casefold() == normalized
            ),
            None,
        )
        selected = exact or (city_suggestions[0] if city_suggestions else None)
        if selected is None:
            return {
                "status": "not_found",
                "query": city_name,
                "suggestions": suggestions,
            }

        city = selected["city"]
        return {
            "status": "ok",
            "query": city_name,
            "city": {
                "id": city["id"],
                "type": 2,
                "name": city.get("name"),
                "address": selected.get("address"),
                "region": (selected.get("region") or {}).get("name"),
                "country": (selected.get("country") or {}).get("name"),
            },
            "suggestions": suggestions,
        }

    def search_trucks(
        self,
        *,
        origin_id: int,
        destination_id: int,
        date_option: str = "today-plus",
        origin_radius_km: int = 0,
        destination_radius_km: int = 0,
        truck_type: int | None = None,
        minimum_firm_rating: int | None = None,
        page: int = 1,
        items_per_page: int = 100,
        demo: bool | None = None,
    ) -> dict[str, Any]:
        """Search free trucks by ATI route and filter parameters."""

        error = self._configuration_error()
        if error:
            return error

        filter_data: dict[str, Any] = {
            "dates": {"date_option": date_option},
            "from": {
                "id": origin_id,
                "type": 2,
                "exact_only": origin_radius_km == 0,
                "radius": origin_radius_km,
            },
            "to": {
                "id": destination_id,
                "type": 2,
                "exact_only": destination_radius_km == 0,
                "radius": destination_radius_km,
            },
            "with_rate": False,
            "change_date": "week",
            "sorting_type": 0,
        }
        if truck_type is not None:
            filter_data["truck_type"] = truck_type
        if minimum_firm_rating is not None:
            filter_data["firm"] = {"firm_rating": minimum_firm_rating}

        response = self._request(
            "POST",
            self.settings.ati_trucks_search_path,
            headers=self._headers(),
            params={"demo": str(self.settings.ati_search_demo_mode if demo is None else demo).lower()},
            json={
                "page": max(page, 0),
                "items_per_page": items_per_page,
                "filter": filter_data,
            },
        )
        return {"status": "ok", "response": response.json()}

    def search_active_carriers(
        self,
        *,
        origin_id: int,
        destination_id: int,
        lookback_days: int = 90,
        truck_type: int | None = None,
        trucks_date_from: datetime | None = None,
        trucks_date_to: datetime | None = None,
        demo: bool | None = None,
    ) -> dict[str, Any]:
        """Search firms active on a route, including searches and truck postings."""

        error = self._configuration_error()
        if error:
            return error

        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "begin_date": (now - timedelta(days=max(1, lookback_days))).isoformat(),
            "from": {"id": origin_id, "type": 2},
            "to": {"id": destination_id, "type": 2},
            "trucks_date_from": (trucks_date_from or now).isoformat(),
        }
        if trucks_date_to is not None:
            payload["trucks_date_to"] = trucks_date_to.isoformat()
        if truck_type is not None:
            payload["truck_type"] = truck_type

        response = self._request(
            "POST",
            self.settings.ati_active_carriers_search_path,
            headers=self._headers(),
            params={"demo": str(self.settings.ati_search_demo_mode if demo is None else demo).lower()},
            json=payload,
        )
        return {"status": "ok", "response": response.json()}
