# Search for nearby places around a location.
# First resolves the location using Nominatim.
# Then searches nearby places using Overpass API.

import logging
from time import perf_counter

from app.clients.places_client import PlacesClient

logger = logging.getLogger(__name__)

def search_nearby_places(
    location: str,
    category: str,
    radius: int = 100000,
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
    # Use the first Nominatim result.
    selected_location = results[0]

    overpass_start = perf_counter()

    # Search nearby places using Overpass.
    nearby_data = client.search_nearby(
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
        "resolved_location": {
            "name": selected_location["name"],
            "address": selected_location["address"],
            "latitude": selected_location["latitude"],
            "longitude": selected_location["longitude"],
        },
        "category": nearby_data["category"],
        "radius_meters": nearby_data["radius_meters"],
        "results": nearby_data["results"],
        "result_count": nearby_data["result_count"],
        "source": "OpenStreetMap Nominatim + Overpass API",
    }
