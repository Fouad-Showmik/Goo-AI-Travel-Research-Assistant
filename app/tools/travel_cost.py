from __future__ import annotations

from app.clients.currency_client import CurrencyClient
from app.services.destination_cost_catalog import DestinationCostCatalog
from app.services.destination_cost_estimator import estimate_catalog_trip_cost

# Shared catalog and currency client instances.
destination_cost_catalog = DestinationCostCatalog()
currency_client = CurrencyClient()

#Estimate trip costs using the destination cost catalog.

def estimate_travel_cost(
    destination: str,
    days: int,
    travelers: int,
    price_tier: str | None = None,
    country: str | None = None,
    budget_amount: float | None = None,
    budget_currency: str | None = None,
    budget_includes_flights: bool = False,
):


    return estimate_catalog_trip_cost(
        catalog=destination_cost_catalog,
        destination=destination,
        country=country,
        price_tier=price_tier,
        travelers=travelers,
        duration_days=days,
        budget_amount=budget_amount,
        budget_currency=budget_currency,
        budget_includes_flights=budget_includes_flights,
        currency_client=currency_client,
    )