#Search for destinations and retrieve their location coordinates.
from app.clients.places_client import PlacesClient


def search_destination(query: str, limit: int = 5):
    return PlacesClient().search(query, limit)