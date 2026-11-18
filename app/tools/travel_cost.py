from __future__ import annotations

import logging
from copy import deepcopy
from threading import Lock
from time import monotonic
from typing import Any

from app.clients.currency_client import CurrencyClient
from app.clients.llm_client import LLMClient, LLMClientError
from app.services.destination_cost_catalog import DestinationCostCatalog
from app.services.destination_cost_estimator import estimate_catalog_trip_cost

logger = logging.getLogger(__name__)

# Shared catalogs and clients.
destination_cost_catalog = DestinationCostCatalog()
currency_client = CurrencyClient()
research_client = LLMClient()

# Cache successful destination research for 30 days.

CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
MAX_CACHE_ENTRIES = 128

_research_cache: dict[
    tuple[str, str, str],
    tuple[float, dict[str, Any]],
                      ] = {}

_cache_lock = Lock()

def _cache_key(
    destination: str,
    country: str | None,
    price_tier: str,
):

    normalize = lambda value: " ".join(
        (value or "").split()
    ).casefold()

    return (
        normalize(destination),
        normalize(country),
        normalize(price_tier),
    )

def _get_cached_research(
    key: tuple[str, str, str],
):

    with _cache_lock:
        cached = _research_cache.get(key)

        if cached is None:
            return None

        expires_at, response = cached

        if monotonic() >= expires_at:
            _research_cache.pop(key, None)
            return None

        return deepcopy(response)

def _save_research(
    key: tuple[str, str, str],
    response: dict[str, Any],
):

    now = monotonic()

    with _cache_lock:
        # Remove expired entries.
        for old_key, (expires_at, _) in list(
            _research_cache.items()
        ):
            if now >= expires_at:
                _research_cache.pop(old_key, None)

        # Keep the cache bounded.
        if (
            key not in _research_cache
            and len(_research_cache) >= MAX_CACHE_ENTRIES
        ):
            oldest_key = min(
                _research_cache,
                key=lambda item: _research_cache[item][0],
            )
            _research_cache.pop(oldest_key, None)

        _research_cache[key] = (
            now + CACHE_TTL_SECONDS,
            deepcopy(response),
        )

#Convert validated web research into the estimator's record format.
def _build_researched_match(
    research: dict[str, Any],
    *,
    country: str | None,
    tier_defaulted: bool,
):

    price_basis = research["price_basis"]

    return {
        "status": "found",
        "destination": research["destination"],
        "country": research.get("country") or country,
        "location_level": research["location_level"],
        "price_tier": research["price_tier"],
        "daily_cost_per_person": research["daily_cost_per_person"],
        "currency": research["currency"],
        "unit": research["unit"],
        "price_basis": price_basis,
        "estimate_label": (
            "published starting price"
            if price_basis == "tier_starting_price_lower_bound"
            else "recorded average daily cost"
        ),
        "tier_defaulted_to_mid_range": tier_defaulted,
        "source_name": research["source_title"],
        "source_url": research["source_url"],
        "license": None,
        "data_version": None,
    }




#Estimate costs using the catalog, with live research fallback.

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
   
    estimator_args = {
        "catalog": destination_cost_catalog,
        "destination": destination,
        "country": country,
        "price_tier": price_tier,
        "travelers": travelers,
        "duration_days": days,
        "budget_amount": budget_amount,
        "budget_currency": budget_currency,
        "budget_includes_flights": budget_includes_flights,
        "currency_client": currency_client,
    }

    # 1. Try the existing catalog first.
    catalog_result = estimate_catalog_trip_cost(**estimator_args)

    # Preserve catalog matches and ambiguous-city results.
    if catalog_result.get("status") != "catalog_miss":
        return catalog_result

    # 2. Determine the effective spending tier.
    effective_tier = price_tier or "mid_range"
    tier_defaulted = price_tier is None

    key = _cache_key(
        destination,
        country,
        effective_tier,
    )

    # 3. Check the research cache.
    research_response = _get_cached_research(key)
    cache_hit = research_response is not None

    # 4. Run live research only when there is no cached result.
    if research_response is None:
        try:
            research_response = research_client.research_destination_cost(
                destination=destination,
                country=country,
                price_tier=effective_tier,
            )

        except LLMClientError:
            logger.exception(
                "Destination cost research failed for %s",
                destination,
            )

            return {
                "status": "research_failed",
                "destination": destination,
                "message": (
                    "No catalog record was available, and live "
                    "destination cost research could not be completed."
                ),
            }

    research = research_response.get("research")

    if not isinstance(research, dict):
        return {
            "status": "research_failed",
            "destination": destination,
            "message": "Destination cost research returned an invalid result.",
        }

    # 5. Do not estimate or cache unsuccessful research.
    if research.get("status") != "found":
        return {
            "status": "research_not_found",
            "destination": destination,
            "message": research.get("notes") or (
                "No reliable daily travel-cost estimate was found."
            ),
            "research": research,
            "sources": research_response.get("sources", []),
        }

    # 6. Normalize the research fields.
    try:
        researched_match = _build_researched_match(
            research,
            country=country,
            tier_defaulted=tier_defaulted,
        )

    except (KeyError, TypeError, ValueError):
        logger.exception(
            "Could not normalize destination cost research for %s",
            destination,
        )

        return {
            "status": "research_failed",
            "destination": destination,
            "message": "The researched cost result could not be normalized.",
        }

    # 7. Cache only successful, validated research.
    if not cache_hit:
        _save_research(key, research_response)

    # 8. Reuse the existing deterministic estimator.
    result = estimate_catalog_trip_cost(
        **estimator_args,
        researched_match=researched_match,
    )

    # 9. Preserve research evidence and provenance.
    result["source"].update({
        "evidence": research.get("source_evidence"),
        "published_date": research.get("published_date"),
        "included_components": research.get("included_components", []),
        "excluded_items": research.get("excluded_items", []),
        "notes": research.get("notes"),
    })

    result["supporting_sources"] = research_response.get("sources", [])

    result["research_metadata"] = {
        "method": "live_web_search",
        "cache_hit": cache_hit,
        "search_call_count": research_response.get("search_call_count"),
    }

    return result