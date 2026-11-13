import logging
import time
from typing import ClassVar

import requests

from app.clients.errors import ExternalAPIError

logger = logging.getLogger(__name__)


class PlacesClient:
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "GooTravelResearchAssistant/0.1"}

    # Supported nearby-place categories
    CATEGORIES: ClassVar[dict[str, list[str]]] = {
        # Food and accommodation
        "restaurant": [
            '["amenity"="restaurant"]',
        ],
        "cafe": [
            '["amenity"="cafe"]',
        ],
        "hotel": [
            '["tourism"="hotel"]',
        ],
        # General sightseeing
        "attraction": [
            '["tourism"="attraction"]',
        ],
        "museum": [
            '["tourism"="museum"]',
        ],
        "viewpoint": [
            '["tourism"="viewpoint"]',
        ],
        "historical_site": [
            '["historic"="monument"]',
            '["historic"="memorial"]',
            '["historic"="castle"]',
            '["historic"="ruins"]',
            '["historic"="archaeological_site"]',
        ],
        # Nature and outdoor activities
        "beach": [
            '["natural"="beach"]',
        ],
        "waterfall": [
            '["waterway"="waterfall"]',
        ],
        "park": [
            '["leisure"="park"]',
            '["leisure"="garden"]',
        ],
        "picnic_site": [
            '["tourism"="picnic_site"]',
        ],
        "camp_site": [
            '["tourism"="camp_site"]',
        ],
        # Entertainment and culture
        "zoo": [
            '["tourism"="zoo"]',
        ],
        "aquarium": [
            '["tourism"="aquarium"]',
        ],
        "theme_park": [
            '["tourism"="theme_park"]',
        ],
        "gallery": [
            '["tourism"="gallery"]',
        ],
        "artwork": [
            '["tourism"="artwork"]',
        ],
    }

    # Returns location details including latitude and longitude.
    def search(self, query: str, limit: int = 5):
        try:
            response = requests.get(
                self.NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": limit,
                },
                headers=self.HEADERS,
                timeout=15,
            )
            response.raise_for_status()

            results = response.json()

            return {
                "query": query,
                "results": [
                    {
                        "name": (
                            item.get("name")
                            or item.get("display_name", "Unknown place")
                        ),
                        "osm_category": item.get("category"),
                        "osm_value": item.get("type"),
                        "address": item.get("display_name"),
                        "latitude": float(item["lat"]),
                        "longitude": float(item["lon"]),
                        "osm_type": item.get("osm_type"),
                        "osm_id": item.get("osm_id"),
                    }
                    for item in results
                ],
                "source": "OpenStreetMap Nominatim",
            }

        except (
            requests.RequestException,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            logger.exception("Places search failed")
            raise ExternalAPIError("Place search is temporarily unavailable.") from exc

    # Search for nearby places using Overpass API.
    # Send an Overpass request with two retry for transient failures.
    def _post_overpass(self, query: str) -> requests.Response:

        max_retries = 2

        retryable_status_codes = {
            429,  # Too Many Requests
            500,  # Internal Server Error
            502,  # Bad Gateway
            503,  # Service Unavailable
            504,  # Gateway Timeout
        }

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    self.OVERPASS_URL,
                    data={"data": query},
                    headers=self.HEADERS,
                    timeout=(10, 45),
                )

                response.raise_for_status()

                return response

            except requests.HTTPError as exc:
                status_code = (
                    exc.response.status_code
                    if exc.response is not None
                    else None
                )

                # Retry only recognized temporary HTTP failures.
                if status_code not in retryable_status_codes:
                    raise

                if attempt >= max_retries:
                    logger.error(
                        "Overpass request failed after %s attempts. "
                        "Final HTTP status: %s",
                        max_retries + 1,
                        status_code,
                    )
                    raise

                delay = 2 ** (attempt + 1)

                logger.warning(
                    "Overpass returned HTTP %s. "
                    "Retrying in %s seconds (%s/%s).",
                    status_code,
                    delay,
                    attempt + 1,
                    max_retries,
                )

                time.sleep(delay)

            except requests.ConnectionError:
                if attempt >= max_retries:
                    raise

                delay = 2 ** (attempt + 1)

                logger.warning(
                    "Overpass connection failed. "
                    "Retrying in %s seconds (%s/%s).",
                    delay,
                    attempt + 1,
                    max_retries,
                )

                time.sleep(delay)

        raise RuntimeError("Overpass request retries exhausted.")

    def search_nearby(
        self,
        latitude: float,
        longitude: float,
        category: str,
        radius: int = 5000,
        limit: int = 20,
    ):

        if category not in self.CATEGORIES:
            raise ValueError(
                f"Unsupported category: {category}. "
                f"Supported categories: {list(self.CATEGORIES)}"
            )

        if not (-90 <= latitude <= 90):
            raise ValueError("Invalid latitude.")

        if not (-180 <= longitude <= 180):
            raise ValueError("Invalid longitude.")

        if not (100 <= radius <= 10000):
            raise ValueError("Radius must be between 100 and 10000 meters.")

        if not (1 <= limit <= 50):
            raise ValueError("Limit must be between 1 and 50.")

        category_filters = self.CATEGORIES[category]

        query_parts = [
            f"nwr(around:{radius},{latitude},{longitude}){filters};"
            for filters in category_filters
        ]

        query = f"""
        [out:json][timeout:25];
        (
            {" ".join(query_parts)}
        );
        out center qt {limit};
        """

        try:
            response = self._post_overpass(query)

            elements = response.json().get("elements", [])

            places = []

            for item in elements:
                tags = item.get("tags", {})

                # Ways and relations generally return center coordinates.
                coordinates = item.get("center", item)

                if "lat" not in coordinates or "lon" not in coordinates:
                    continue

                places.append(
                    {
                        "name": tags.get("name", "Unnamed place"),
                        "category": category,
                        "address": tags.get("addr:full"),
                        "latitude": coordinates["lat"],
                        "longitude": coordinates["lon"],
                        "osm_type": item.get("type"),
                        "osm_id": item.get("id"),
                    }
                )

                if len(places) >= limit:
                    break

            return {
                "latitude": latitude,
                "longitude": longitude,
                "category": category,
                "radius_meters": radius,
                "results": places,
                "result_count": len(places),
                "source": "OpenStreetMap Overpass API",
            }

        except (
            requests.RequestException,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            logger.exception("Overpass API search failed")

            raise ExternalAPIError(
                "Nearby places search is temporarily unavailable."
            ) from exc
