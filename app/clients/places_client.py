import logging
import threading
import time
from copy import deepcopy
from typing import Any, ClassVar

import requests

from app.clients.errors import ExternalAPIError
from app.core.config import settings

logger = logging.getLogger(__name__)


class PlacesClient:
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    NOMINATIM_LOOKUP_URL = "https://nominatim.openstreetmap.org/lookup"
    OVERPASS_URL = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
    GEOAPIFY_GEOCODING_URL = "https://api.geoapify.com/v1/geocode/search"
    GEOAPIFY_BOUNDARIES_URL = "https://api.geoapify.com/v1/boundaries/part-of"

    # Destination geocoding cache.
    GEOCODING_CACHE_TTL: ClassVar[int] = 24 * 60 * 60
    GEOCODING_CACHE_MAX_ITEMS: ClassVar[int] = 256

    _GEOCODING_CACHE_LOCK: ClassVar[threading.Lock] = (
        threading.Lock()
    )

    _GEOCODING_CACHE: ClassVar[
        dict[tuple[str, int], tuple[float, dict[str, Any]]]
    ] = {}

    # Country-boundary cache.
    _COUNTRY_BOUNDARY_CACHE_TTL: ClassVar[int] = 24 * 60 * 60

    _COUNTRY_BOUNDARY_CACHE_LOCK: ClassVar[threading.Lock] = (
        threading.Lock()
    )

    _COUNTRY_BOUNDARY_CACHE: ClassVar[
        dict[tuple[str, str], tuple[float, dict[str, Any]]]
    ] = {}

    # Overpass request configuration.
    OVERPASS_TIMEOUT: ClassVar[tuple[int, int]] = (5, 15)

    # One retry means two total attempts.
    OVERPASS_MAX_RETRIES: ClassVar[int] = 1

    OVERPASS_RETRY_DELAY_SECONDS: ClassVar[int] = 1

    # Skip Overpass temporarily after repeated failures.
    OVERPASS_COOLDOWN_SECONDS: ClassVar[int] = 120

    # Shared circuit-breaker state across PlacesClient instances.
    _OVERPASS_STATE_LOCK: ClassVar[threading.Lock] = threading.Lock()

    _OVERPASS_UNAVAILABLE_UNTIL: ClassVar[float] = 0.0

    GEOAPIFY_CATEGORIES: ClassVar[dict[str, tuple[str, ...]]] = {
        "all_attractions": (
            "tourism.attraction",
            "tourism.sights",
            "entertainment.museum",
            "entertainment.culture",
            "leisure.park",
            "leisure.park.nature_reserve",
            "national_park",
            "beach",
            "natural",
            "entertainment.zoo",
            "entertainment.aquarium",
            "entertainment.theme_park",
            "camping.camp_site",
        ),
        "attraction": ("tourism.attraction", "tourism.sights"),
        "museum": ("entertainment.museum",),
        "viewpoint": ("tourism.attraction.viewpoint",),
        "beach": ("beach",),
        "waterfall": ("natural.water",),
        "park": (
            "leisure.park",
            "leisure.park.nature_reserve",
            "national_park",
        ),
        "picnic_site": ("leisure.picnic.picnic_site",),
        "camp_site": ("camping.camp_site",),
        "zoo": ("entertainment.zoo",),
        "aquarium": ("entertainment.aquarium",),
        "theme_park": ("entertainment.theme_park",),
        "gallery": ("entertainment.culture.gallery",),
        "artwork": ("tourism.attraction.artwork",),
        "historical_site": (
            "tourism.sights.archaeological_site",
            "tourism.sights.castle",
            "tourism.sights.memorial.monument",
            "tourism.sights.monastery",
        ),
        "religious_site": (
            "tourism.sights.place_of_worship.temple",
            "tourism.sights.place_of_worship.shrine",
            "religion.place_of_worship.buddhism",
            "religion.place_of_worship.shinto",
        ),
    }

    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "GooTravelResearchAssistant/0.1"}

    # Nominatim rate limiting and caching.
    _NOMINATIM_LOCK: ClassVar[threading.Lock] = threading.Lock()

    _NOMINATIM_LAST_REQUEST: ClassVar[float] = 0.0

    _NOMINATIM_CACHE: ClassVar[
        dict[tuple[str, int], tuple[float, dict[str, Any]]]
    ] = {}

    NOMINATIM_REQUEST_INTERVAL: ClassVar[float] = 1.1
    NOMINATIM_CACHE_TTL: ClassVar[int] = 86400  # 24 hours
    NOMINATIM_MAX_CACHE_ITEMS: ClassVar[int] = 256

    # Nearby-place result caching.
    NEARBY_CACHE_TTL: ClassVar[int] = 30 * 24 * 60 * 60
    NEARBY_CACHE_MAX_ITEMS: ClassVar[int] = 512

    _NEARBY_CACHE_LOCK: ClassVar[threading.Lock] = threading.Lock()

    _NEARBY_CACHE: ClassVar[
        dict[tuple[Any, ...], tuple[float, dict[str, Any]]]
    ] = {}

    # Supported nearby-place categories
    CATEGORIES: ClassVar[dict[str, list[str]]] = {
        "all_attractions": [
            '["tourism"="attraction"]["name"]',
            '["tourism"="museum"]["name"]',
            '["tourism"="viewpoint"]["name"]',
            '["historic"="monument"]["name"]',
            '["historic"="castle"]["name"]',
            '["historic"="ruins"]["name"]',
        ],
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
            '["historic"="castle"]["name"]',
            '["historic"="building"]["name"]',
            '["historic"="ruins"]["name"]',
            '["historic"="archaeological_site"]["name"]',
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
        "religious_site": [
            '["amenity"="place_of_worship"]["religion"="buddhist"]["name"]',
            '["amenity"="place_of_worship"]["religion"="shinto"]["name"]',
            '["building"="temple"]["name"]',
            '["historic"="wayside_shrine"]["name"]',
        ],
    }

    COUNTRY_SEARCH_CATEGORIES: ClassVar[frozenset[str]] = frozenset({
    "all_attractions",
    "attraction",
    "museum",
    "viewpoint",
    "historical_site",
    "beach",
    "waterfall",
    "park",
    "picnic_site",
    "camp_site",
    "zoo",
    "aquarium",
    "theme_park",
    "gallery",
    "artwork",
    "religious_site",
    })

    
    @classmethod
    def _get_nearby_cache(
        cls,
        key: tuple[Any, ...],
    ) -> dict[str, Any] | None:
        """Return an unexpired cached nearby-place result."""

        with cls._NEARBY_CACHE_LOCK:
            cached = cls._NEARBY_CACHE.get(key)

            if cached is None:
                return None

            expires_at, result = cached

            if time.monotonic() >= expires_at:
                cls._NEARBY_CACHE.pop(key, None)
                return None

            # Prevent callers from modifying the cached object.
            return deepcopy(result)


    @classmethod
    def _save_nearby_cache(
        cls,
        key: tuple[Any, ...],
        result: dict[str, Any],
    ) -> None:
        """Cache successful, non-empty nearby-place results."""

        if not isinstance(result, dict):
            return

        if not result.get("result_count", 0):
            return

        now = time.monotonic()

        with cls._NEARBY_CACHE_LOCK:

            # Remove expired entries.
            expired_keys = [
                old_key
                for old_key, (expires_at, _) in cls._NEARBY_CACHE.items()
                if now >= expires_at
            ]

            for old_key in expired_keys:
                cls._NEARBY_CACHE.pop(old_key, None)

            # Keep cache memory bounded.
            if (
                key not in cls._NEARBY_CACHE
                and len(cls._NEARBY_CACHE) >= cls.NEARBY_CACHE_MAX_ITEMS
            ):
                oldest_key = min(
                    cls._NEARBY_CACHE,
                    key=lambda item: cls._NEARBY_CACHE[item][0],
                )

                cls._NEARBY_CACHE.pop(oldest_key, None)

            cls._NEARBY_CACHE[key] = (
                now + cls.NEARBY_CACHE_TTL,
                deepcopy(result),
            )


    #Fetch Nominatim data with rate limiting and caching.

    @classmethod
    def _get_nominatim_data(
        cls,
        query: str,
        limit: int,
    ):

        cache_key = (query.strip().casefold(), limit)

        with cls._NOMINATIM_LOCK:

            # Check the cache first.
            now = time.monotonic()
            cached = cls._NOMINATIM_CACHE.get(cache_key)

            if cached:
                cached_time, cached_data = cached

                if now - cached_time < cls.NOMINATIM_CACHE_TTL:
                    return cached_data

                del cls._NOMINATIM_CACHE[cache_key]

            # Enforce the minimum interval between requests.
            elapsed = now - cls._NOMINATIM_LAST_REQUEST

            if elapsed < cls.NOMINATIM_REQUEST_INTERVAL:
                time.sleep(cls.NOMINATIM_REQUEST_INTERVAL - elapsed)

            # Record the request time.
            cls._NOMINATIM_LAST_REQUEST = time.monotonic()

            response = requests.get(
                cls.NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "geocodejson",
                    "addressdetails": 1,
                    "limit": limit,
                },
                headers=cls.HEADERS,
                timeout=15,
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):
                raise TypeError("Invalid Nominatim response.")

            # Store the response in the cache.
            cls._NOMINATIM_CACHE[cache_key] = (
                time.monotonic(),
                data,
            )

            # Prevent unlimited cache growth.
            if len(cls._NOMINATIM_CACHE) > cls.NOMINATIM_MAX_CACHE_ITEMS:
                oldest_key = next(iter(cls._NOMINATIM_CACHE))
                del cls._NOMINATIM_CACHE[oldest_key]

            return data
    

    #Retrieve and cache a country's GeoJSON boundary.
    @classmethod
    def _get_country_geometry(
        cls,
        *,
        country_name: str,
        place_id: str | None,
        latitude: float | None,
        longitude: float | None,
    ) -> dict[str, Any]:

        api_key = settings.geoapify_api_key

        if not api_key:
            raise ExternalAPIError(
                "Geoapify API key is not configured."
            )

        if not place_id and (
            latitude is None or longitude is None
        ):
            raise ValueError(
                "A country place ID or coordinates are required."
            )

        lookup_key = (
            str(place_id)
            if place_id
            else f"{latitude},{longitude}"
        )

        cache_key = (
            lookup_key,
            country_name.strip().casefold(),
        )

        with cls._COUNTRY_BOUNDARY_CACHE_LOCK:

            cached = cls._COUNTRY_BOUNDARY_CACHE.get(cache_key)

            if cached:
                cached_time, geometry = cached

                if (
                    time.monotonic() - cached_time
                    < cls._COUNTRY_BOUNDARY_CACHE_TTL
                ):
                    return deepcopy(geometry)

                cls._COUNTRY_BOUNDARY_CACHE.pop(cache_key, None)

        params = {
            "boundaries": "administrative",
            "geometry": "geometry_1000",
            "lang": "en",
            "apiKey": api_key,
        }

        # Use exactly one lookup method: place ID or coordinates.
        if place_id:
            params["id"] = place_id
        else:
            params["lat"] = latitude
            params["lon"] = longitude

        try:
            response = requests.get(
                cls.GEOAPIFY_BOUNDARIES_URL,
                params=params,
                headers=cls.HEADERS,
                timeout=(10, 40),
            )

            response.raise_for_status()

            payload = response.json()

            if not isinstance(payload, dict):
                raise TypeError(
                    "Invalid Geoapify boundaries response."
                )

            expected_name = country_name.strip().casefold()


            for feature in payload.get("features", []):

                properties = feature.get("properties") or {}
                geometry = feature.get("geometry") or {}

                feature_place_id = properties.get("place_id")

                feature_name = (
                    properties.get("name") or ""
                ).strip().casefold()

                feature_formatted = (
                    properties.get("formatted") or ""
                ).strip().casefold()

                # Prefer the exact Geoapify place ID.
                # Fall back to either the native or formatted country name.
                matches_country = (
                    bool(place_id)
                    and feature_place_id == place_id
                ) or (
                    expected_name in {
                        feature_name,
                        feature_formatted,
                    }
                )

                if not matches_country:
                    continue

                if geometry.get("type") not in {
                    "Polygon",
                    "MultiPolygon",
                }:
                    continue

                with cls._COUNTRY_BOUNDARY_CACHE_LOCK:
                    cls._COUNTRY_BOUNDARY_CACHE[cache_key] = (
                        time.monotonic(),
                        deepcopy(geometry),
                    )

                return geometry


            raise ValueError(
                f"Country boundary not found for '{country_name}'."
            )

        except requests.RequestException as exc:

            status_code = getattr(
                getattr(exc, "response", None),
                "status_code",
                None,
            )

            logger.error(
                "Geoapify country boundary request failed. "
                "HTTP status: %s",
                status_code,
            )

            raise ExternalAPIError(
                "Country boundary lookup is temporarily unavailable."
            ) from None

        except (KeyError, TypeError, ValueError):

            logger.exception(
                "Geoapify country boundary processing failed."
            )

            raise ExternalAPIError(
                "A valid country boundary could not be retrieved."
            ) from None

    #Normalize Polygon and MultiPolygon GeoJSON geometries.
    @staticmethod
    def _get_polygon_parts(
        geometry: dict[str, Any],
    ):

        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")

        if geometry_type == "Polygon":
            return [coordinates]

        if geometry_type == "MultiPolygon":
            return coordinates

        raise ValueError(
            f"Unsupported country geometry: {geometry_type}"
        )

    #Check whether a coordinate falls inside a polygon ring.
    @staticmethod
    def _point_in_ring(
        longitude: float,
        latitude: float,
        ring: list[list[float]],
    ):

        if len(ring) < 4:
            return False

        inside = False
        previous = len(ring) - 1

        for current in range(len(ring)):
            x1, y1 = ring[current][:2]
            x2, y2 = ring[previous][:2]

            intersects = (
                (y1 > latitude) != (y2 > latitude)
            ) and (
                longitude
                < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            )

            if intersects:
                inside = not inside

            previous = current

        return inside

    #Check whether a point is inside the country boundary.
    @classmethod
    def _point_in_country(
        cls,
        longitude: float,
        latitude: float,
        geometry: dict[str, Any],
    ):

        polygons = cls._get_polygon_parts(geometry)

        for polygon in polygons:
            if not polygon:
                continue

            # First ring represents the outer boundary.
            outer_ring = polygon[0]

            if not cls._point_in_ring(
                longitude,
                latitude,
                outer_ring,
            ):
                continue

            # Remaining rings represent holes.
            inside_hole = any(
                cls._point_in_ring(longitude, latitude, hole)
                for hole in polygon[1:]
            )

            if not inside_hole:
                return True

        return False

    #Calculate the country's bounding box.
    @classmethod
    def _get_country_bbox(
        cls,
        geometry: dict[str, Any],
    ):

        polygons = cls._get_polygon_parts(geometry)

        points = [
            point[:2]
            for polygon in polygons
            for ring in polygon
            for point in ring
            if len(point) >= 2
        ]

        if not points:
            raise ValueError(
                "Country boundary contains no coordinates."
            )

        longitudes = [point[0] for point in points]
        latitudes = [point[1] for point in points]

        return (
            min(longitudes),
            min(latitudes),
            max(longitudes),
            max(latitudes),
        )

    @classmethod
    def _get_geoapify_geocoding_data(
        cls,
        query: str,
        limit: int,
    ) -> dict[str, Any]:

        api_key = settings.geoapify_api_key

        if not api_key:
            raise ExternalAPIError(
                "Geoapify API key is not configured."
            )

        cache_key = (query.strip().casefold(), limit)

        with cls._GEOCODING_CACHE_LOCK:

            now = time.monotonic()
            cached = cls._GEOCODING_CACHE.get(cache_key)

            if cached:
                cached_time, cached_data = cached

                if now - cached_time < cls.GEOCODING_CACHE_TTL:
                    logger.info(
                        "Geocoding cache hit | Query: %s",
                        query,
                    )
                    return deepcopy(cached_data)

                cls._GEOCODING_CACHE.pop(cache_key, None)

            try:
                response = requests.get(
                    cls.GEOAPIFY_GEOCODING_URL,
                    params={
                        "text": query,
                        "format": "json",
                        "limit": limit,
                        "lang": "en",
                        "apiKey": api_key,
                    },
                    headers=cls.HEADERS,
                    timeout=(10, 20),
                )

                response.raise_for_status()

                payload = response.json()

                if not isinstance(payload, dict):
                    raise TypeError(
                        "Invalid Geoapify geocoding response."
                    )

                results = []

                for item in payload.get("results", []):

                    if not isinstance(item, dict):
                        continue

                    try:
                        latitude = float(item["lat"])
                        longitude = float(item["lon"])
                    except (KeyError, TypeError, ValueError):
                        continue

                    datasource = item.get("datasource")
                    if not isinstance(datasource, dict):
                        datasource = {}

                    raw = datasource.get("raw")
                    if not isinstance(raw, dict):
                        raw = {}

                    results.append({
                        "name": (
                            item.get("name")
                            or item.get("address_line1")
                            or item.get("formatted")
                            or query
                        ),
                        "osm_category": raw.get("osm_key"),
                        "osm_value": raw.get("osm_value"),
                        "place_type": (
                            item.get("result_type")
                            or item.get("type")
                        ),
                        "address": (
                            item.get("formatted")
                            or item.get("address_line1")
                        ),
                        "country": item.get("country"),
                        "state": item.get("state"),
                        "city": item.get("city"),
                        "latitude": latitude,
                        "longitude": longitude,
                        "osm_type": raw.get("osm_type"),
                        "osm_id": raw.get("osm_id"),
                        "place_id": item.get("place_id"),
                    })

                result = {
                    "query": query,
                    "results": results,
                    "source": "Geoapify Geocoding API",
                    "attribution": "Powered by Geoapify",
                    "attribution_url": "https://www.geoapify.com/",
                }

                # Cache successful lookups only.
                if results:

                    cls._GEOCODING_CACHE[cache_key] = (
                        time.monotonic(),
                        deepcopy(result),
                    )

                    if (
                        len(cls._GEOCODING_CACHE)
                        > cls.GEOCODING_CACHE_MAX_ITEMS
                    ):
                        oldest_key = min(
                            cls._GEOCODING_CACHE,
                            key=lambda key: cls._GEOCODING_CACHE[key][0],
                        )
                        cls._GEOCODING_CACHE.pop(oldest_key, None)

                logger.info(
                    "Geoapify geocoding completed | Query: %s | "
                    "Results: %s",
                    query,
                    len(results),
                )

                return result

            except requests.RequestException as exc:

                status_code = getattr(
                    getattr(exc, "response", None),
                    "status_code",
                    None,
                )

                # Do not log the URL because it may contain the API key.
                logger.error(
                    "Geoapify geocoding failed. HTTP status: %s",
                    status_code,
                )

                raise ExternalAPIError(
                    "Destination geocoding is temporarily unavailable."
                ) from None

            except (KeyError, TypeError, ValueError):

                logger.exception(
                    "Geoapify returned an invalid geocoding response."
                )

                raise ExternalAPIError(
                    "Geoapify returned an invalid geocoding response."
                ) from None

    # Resolve a geographic location using Nominatim GeoCodeJSON
# Resolve a geographic location using Geoapify.
    def search(self, query: str, limit: int = 5):

        return self._get_geoapify_geocoding_data(
            query=query,
            limit=limit,
        )

    @classmethod
    def _overpass_cooldown_remaining(cls) -> float:
        with cls._OVERPASS_STATE_LOCK:
            return max(
                0.0,
                cls._OVERPASS_UNAVAILABLE_UNTIL - time.monotonic(),
            )

    @classmethod
    def _open_overpass_circuit(cls):
        with cls._OVERPASS_STATE_LOCK:
            cls._OVERPASS_UNAVAILABLE_UNTIL = (
                time.monotonic() + cls.OVERPASS_COOLDOWN_SECONDS
            )

        logger.error(
            "Overpass unavailable after repeated failures. "
            "Circuit opened for %s seconds.",
            cls.OVERPASS_COOLDOWN_SECONDS,
        )


    # Search for nearby places using Overpass API.
    # Send an Overpass request with two retry for transient failures.
    def _post_overpass(
    self,
    query: str,
    timeout: tuple[int, int] | None = None,
    max_retries: int | None = None,
    ):
        cls = type(self)

        if timeout is None:
            timeout = cls.OVERPASS_TIMEOUT

        if max_retries is None:
            max_retries = cls.OVERPASS_MAX_RETRIES

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
                    timeout=timeout,
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
                    cls._open_overpass_circuit()
                    raise

                delay = cls.OVERPASS_RETRY_DELAY_SECONDS

                logger.warning(
                    "Overpass returned HTTP %s. "
                    "Retrying in %s seconds (%s/%s).",
                    status_code,
                    delay,
                    attempt + 1,
                    max_retries,
                )

                time.sleep(delay)

            except (requests.Timeout, requests.ConnectionError) as exc:

                if attempt >= max_retries:
                    logger.error(
                        "Overpass request failed after %s attempts: %s",
                        max_retries + 1,
                        type(exc).__name__,
                    )
                    cls._open_overpass_circuit()
                    raise

                delay = cls.OVERPASS_RETRY_DELAY_SECONDS

                logger.warning(
                    "Overpass request failed (%s). "
                    "Retrying in %s seconds (%s/%s).",
                    type(exc).__name__,
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
                        "name": tags.get("name:en") or tags.get("name", "Unnamed place"),
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
                "attribution": "© OpenStreetMap contributors",
                "attribution_url": "https://www.openstreetmap.org/copyright",
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


    def search_nearby_geoapify(
    self,
    latitude: float,
    longitude: float,
    category: str,
    radius: int = 5000,
    limit: int = 20,
):
        if category not in self.GEOAPIFY_CATEGORIES:
            raise ValueError(f"Unsupported category: {category}")

        api_key = settings.geoapify_api_key

        if not api_key:
            raise ExternalAPIError(
                "Geoapify API key is not configured."
            )

        params = {
            "categories": ",".join(
                self.GEOAPIFY_CATEGORIES[category]
            ),
            "conditions": "named",
            "filter": (
                f"circle:{longitude},{latitude},{radius}"
            ),
            "bias": f"proximity:{longitude},{latitude}",
            "limit": limit,
            "lang": "en",
            "apiKey": api_key,
        }

        try:
            response = requests.get(
                self.GEOAPIFY_PLACES_URL,
                params=params,
                timeout=(10, 25),
            )

            response.raise_for_status()

            data = response.json()
            places = []

            for feature in data.get("features", []):
                properties = feature.get("properties") or {}
                geometry = feature.get("geometry") or {}
                coordinates = geometry.get("coordinates") or []

                if len(coordinates) < 2:
                    continue

                name = (
                    properties.get("name")
                    or properties.get("address_line1")
                )

                if not name:
                    continue

                places.append({
                    "name": name,
                    "category": category,
                    "categories": properties.get("categories", []),
                    "address": properties.get("formatted"),
                    "latitude": float(coordinates[1]),
                    "longitude": float(coordinates[0]),
                    "place_id": properties.get("place_id"),
                })

            return {
                "latitude": latitude,
                "longitude": longitude,
                "category": category,
                "radius_meters": radius,
                "results": places,
                "result_count": len(places),
                "source": "Geoapify Places API",
                "attribution": "Powered by Geoapify",
                "attribution_url": "https://www.geoapify.com/",
            }

        except requests.RequestException as exc:
            status_code = getattr(
                getattr(exc, "response", None),
                "status_code",
                None,
            )

            logger.error(
                "Geoapify nearby search failed. HTTP status: %s",
                status_code,
            )

            raise ExternalAPIError(
                "Geoapify nearby search is temporarily unavailable."
            ) from None

        except (KeyError, TypeError, ValueError) as exc:
            logger.exception("Geoapify response processing failed")

            raise ExternalAPIError(
                "Geoapify returned an invalid places response."
            ) from exc

    #Search nearby places, reusing cached results when available.
    def search_nearby_with_fallback(
        self,
        latitude: float,
        longitude: float,
        category: str,
        radius: int = 5000,
        limit: int = 20,
    ):

        cooldown_remaining = (
            type(self)._overpass_cooldown_remaining()
        )

        if cooldown_remaining > 0:

            logger.warning(
                "Skipping Overpass because its circuit breaker "
                "is active. Using Geoapify directly."
            )

        else:

            try:
                result = self.search_nearby(
                    latitude=latitude,
                    longitude=longitude,
                    category=category,
                    radius=radius,
                    limit=limit,
                )

                if result.get("result_count", 0) > 0:
                    return result

                logger.warning(
                    "Overpass returned no matching places. "
                    "Switching to Geoapify fallback."
                )

            except ExternalAPIError:

                logger.warning(
                    "Overpass unavailable. "
                    "Switching to Geoapify fallback."
                )

        return self.search_nearby_geoapify(
            latitude=latitude,
            longitude=longitude,
            category=category,
            radius=radius,
            limit=limit,
        )


    #Get the best available administrative area label from OSM tags.
    @staticmethod
    def _get_region_label(tags: dict[str, Any]):

        region_keys = (
            "addr:state",
            "addr:province",
            "addr:region",
            "addr:county",
            "addr:district",
            "addr:municipality",
            "addr:city",
            "addr:town",
        )

        for key in region_keys:
            value = tags.get(key)

            if value:
                return value

        return "Region not specified"


    #Determine the specific category when all attractions are requested.
    @staticmethod
    def _get_attraction_category(
        tags: dict[str, Any],
        requested_category: str,
        ):

        if requested_category != "all_attractions":
            return requested_category

        tourism_value = tags.get("tourism")

        if tourism_value in {
            "attraction",
            "museum",
            "viewpoint",
            "picnic_site",
            "camp_site",
            "zoo",
            "aquarium",
            "theme_park",
            "gallery",
            "artwork",
        }:
            return tourism_value

        if tags.get("historic"):
            return "historical_site"

        if tags.get("natural") == "beach":
            return "beach"

        if (
            tags.get("natural") == "waterfall"
            or tags.get("waterway") == "waterfall"
        ):
            return "waterfall"

        if tags.get("leisure") in {"park", "garden"}:
            return "park"

        return "attraction"


    #Search country-wide attractions using Geoapify.
    def search_country_attractions(
        self,
        country: dict[str, Any],
        category: str,
        limit: int = 50,
    ):
        """Search country-wide attractions using Geoapify."""

        if category not in self.COUNTRY_SEARCH_CATEGORIES:
            raise ValueError(
                f"Unsupported country category: {category}"
            )

        if not (1 <= limit <= 50):
            raise ValueError(
                "Country search limit must be between 1 and 50."
            )

        api_key = settings.geoapify_api_key

        if not api_key:
            raise ExternalAPIError(
                "Geoapify API key is not configured."
            )

        country_name = (
            country.get("country")
            or country.get("name")
            or "Unknown country"
        )

        place_id = country.get("place_id")
        latitude = country.get("latitude")
        longitude = country.get("longitude")

        if not place_id and (
            latitude is None or longitude is None
        ):
            raise ValueError(
                "A usable country boundary location was not found."
            )

        cache_key = (
            "country",
            str(place_id or f"{latitude},{longitude}"),
            category,
            limit,
        )

        cached_result = self._get_nearby_cache(cache_key)

        if cached_result is not None:
            logger.info(
                "Country attraction cache hit | Country: %s | "
                "Category: %s | Results: %s",
                country_name,
                category,
                cached_result.get("result_count", 0),
            )

            return cached_result

        try:
            # 1. Retrieve the actual country polygon.
            geometry = self._get_country_geometry(
                country_name=country_name,
                place_id=place_id,
                latitude=latitude,
                longitude=longitude,
            )
            # 2. Select Geoapify categories.
            categories = self.GEOAPIFY_CATEGORIES[category]

            # Use the Geoapify place boundary when a place ID is
            # available. Fall back to the country bounding box when
            # the geocoding result only provides coordinates.
            if place_id:
                spatial_filter = f"place:{place_id}"
            else:
                lon_min, lat_min, lon_max, lat_max = (
                    self._get_country_bbox(geometry)
                )
                spatial_filter = (
                    f"rect:{lon_min},{lat_min},{lon_max},{lat_max}"
                )

            api_limit = 100

            params = {
                "categories": ",".join(categories),
                "conditions": "named",
                "filter": spatial_filter,
                "limit": api_limit,
                "lang": "en",
                "apiKey": api_key,
            }

            # 4. Request places from Geoapify.
            response = requests.get(
                self.GEOAPIFY_PLACES_URL,
                params=params,
                timeout=(10, 40),
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):
                raise TypeError("Invalid Geoapify response format.")

            features = data.get("features", [])

            # 5. Filter and normalize places.
            places = []
            seen = set()

            for feature in features:
                properties = feature.get("properties") or {}
                point_geometry = feature.get("geometry") or {}

                coordinates = point_geometry.get("coordinates") or []

                if (
                    point_geometry.get("type") != "Point"
                    or len(coordinates) < 2
                ):
                    continue

                try:
                    longitude = float(coordinates[0])
                    latitude = float(coordinates[1])
                except (TypeError, ValueError):
                    continue

                # Keep only results inside the actual country polygon.
                if not self._point_in_country(
                    longitude,
                    latitude,
                    geometry,
                ):
                    continue

                name = (
                    properties.get("name")
                    or properties.get("address_line1")
                )

                if not name:
                    continue

                place_id = properties.get("place_id")

                unique_key = place_id or (
                    name,
                    latitude,
                    longitude,
                )

                if unique_key in seen:
                    continue

                seen.add(unique_key)

                region = (
                    properties.get("state")
                    or properties.get("county")
                    or "Region not specified"
                )

                places.append({
                    "name": name,
                    "category": category,
                    "categories": properties.get("categories", []),
                    "address": properties.get("formatted"),
                    "country": properties.get("country"),
                    "region": region,
                    "city": properties.get("city"),
                    "latitude": latitude,
                    "longitude": longitude,
                    "place_id": place_id,
                })

            # 6. Apply the user's requested result limit.
            places = places[:limit]

            # 7. Organize results by available region.
            grouped_places: dict[str, list[dict[str, Any]]] = {}

            for place in places:
                grouped_places.setdefault(
                    place["region"],
                    [],
                ).append(place)

            region_groups = [
                {
                    "region": region,
                    "result_count": len(region_places),
                    "results": region_places,
                }
                for region, region_places in grouped_places.items()
            ]

            result = {
                "country": country_name,
                "category": category,
                "search_scope": "country",
                "results": places,
                "region_groups": region_groups,
                "result_count": len(places),
                "max_results": limit,
                "may_be_truncated": len(features) >= api_limit,
                "boundary_available": True,
                "coverage_note": (
                    "Results were retrieved from Geoapify and filtered "
                    "against the actual country boundary. The returned "
                    "list is limited and is not exhaustive."
                ),
                "source": "Geoapify Places API",
                "attribution": "Powered by Geoapify",
                "attribution_url": "https://www.geoapify.com/",
                "osm_attribution": "© OpenStreetMap contributors",
                "osm_attribution_url": (
                    "https://www.openstreetmap.org/copyright"
                ),
            }

            self._save_nearby_cache(cache_key, result)
            return result

        except requests.RequestException as exc:
            # Do not log the exception URL because it may contain
            # the Geoapify API key in its query parameters.
            status_code = getattr(
                getattr(exc, "response", None),
                "status_code",
                None,
            )

            logger.error(
                "Geoapify country search request failed. HTTP status: %s",
                status_code,
            )

            raise ExternalAPIError(
                "Country-wide attraction search is temporarily unavailable."
            ) from None

        except (KeyError, TypeError, ValueError) as exc:
            logger.exception("Geoapify country search failed")

            raise ExternalAPIError(
                "Country-wide attraction search is temporarily unavailable."
            ) from exc