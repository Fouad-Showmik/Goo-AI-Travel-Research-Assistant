# Search for places around a location.
# City/region destinations use radius searches.
# Country destinations use country-boundary searches.

import logging
from time import perf_counter

from app.clients.places_client import PlacesClient

logger = logging.getLogger(__name__)


def search_nearby_places(
    location: str,
    category: str,
    radius: int = 5000,
    limit: int = 20,
):
    client = PlacesClient()

    total_start = perf_counter()
    geocoding_start = perf_counter()

    location_data = client.search(location, limit=1)

    geocoding_time = perf_counter() - geocoding_start
    results = location_data.get("results", [])

    if not results:
        return {
            "location_query": location,
            "category": category,
            "results": [],
            "result_count": 0,
            "message": (
                f"No matching location found for '{location}'. "
                "Try providing a more specific location."
            ),
        }

    selected_location = results[0]

    resolved_location = {
        "name": selected_location["name"],
        "address": selected_location["address"],
        "place_type": selected_location["place_type"],
        "latitude": selected_location["latitude"],
        "longitude": selected_location["longitude"],
    }

    overpass_start = perf_counter()

    # Country destination: search within its OSM boundary.
    if selected_location["place_type"] == "country":

        country_data = client.search_country_attractions(
            country=selected_location,
            category=category,
            limit=limit,
        )

        search_time = perf_counter() - overpass_start
        total_time = perf_counter() - total_start

        logger.info(
            "Country attraction search timings | "
            "Geocoding: %.2fs | Overpass: %.2fs | Total: %.2fs",
            geocoding_time,
            search_time,
            total_time,
        )

        return {
            "location_query": location,
            "resolved_location": resolved_location,
            **country_data,
        }

    # City or region destination: use the existing radius search.
# City or region destination: use nearby search with fallback.
    nearby_data = client.search_nearby_with_fallback(
        latitude=selected_location["latitude"],
        longitude=selected_location["longitude"],
        category=category,
        radius=radius,
        limit=limit,
)

    overpass_time = perf_counter() - overpass_start
    total_time = perf_counter() - total_start

    logger.info(
        "Nearby search timings | Geocoding: %.2fs | "
        "Overpass: %.2fs | Total: %.2fs",
        geocoding_time,
        overpass_time,
        total_time,
    )

    return {
        "location_query": location,
        "resolved_location": resolved_location,
        "search_scope": "radius",
        "category": nearby_data["category"],
        "radius_meters": nearby_data["radius_meters"],
        "results": nearby_data["results"],
        "result_count": nearby_data["result_count"],
        "source": nearby_data["source"],
    }