from __future__ import annotations

from decimal import (
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
)
from typing import Any

from app.clients.errors import ExternalAPIError
from app.services.destination_cost_catalog import (
    DestinationCostCatalog,
)

CENT = Decimal("0.01")


def _money(value: Decimal):
    return float(
        value.quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )
    )

#Estimate land-trip cost using an all-inclusive daily rate
def estimate_catalog_trip_cost(
    *,
    catalog: DestinationCostCatalog,
    destination: str,
    travelers: int,
    duration_days: int,
    price_tier: str | None = None,
    country: str | None = None,
    budget_amount: float | str | None = None,
    budget_currency: str | None = None,
    budget_includes_flights: bool = False,
    currency_client: Any | None = None,
    researched_match: dict[str, Any] | None = None,
):

    if travelers < 1:
        raise ValueError(
            "travelers must be at least 1"
        )

    if duration_days < 1:
        raise ValueError(
            "duration_days must be at least 1"
        )

    if researched_match is not None:
        if researched_match.get("status") != "found":
            raise ValueError(
                "A valid researched cost match is required."
            )

        match = researched_match

    else:
        match = catalog.lookup(
            destination=destination,
            price_tier=price_tier,
            country=country,
        )

    if match is None:
        return {
            "status": "catalog_miss",
            "destination": destination,
            "message": (
                "No suitable city or country record exists "
                "in the local catalog. Use the web-search "
                "fallback to research destination costs."
            ),
        }

    if match.get("status") == "ambiguous_city":
        return match

    try:
        daily_cost = Decimal(
            str(match["daily_cost_per_person"])
        )

        land_total = (
            daily_cost
            * Decimal(travelers)
            * Decimal(duration_days)
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
        KeyError,
    ) as exc:
        raise ValueError(
            "The catalog returned an invalid daily cost."
        ) from exc

    source_currency = match["currency"]

    comparison_total = land_total
    comparison_currency = source_currency

    conversion: dict[str, Any] | None = None
    conversion_error: str | None = None

    # Convert the estimated land cost to the user's budget currency.
    if budget_currency:

        target_currency = budget_currency.upper()

        if target_currency != source_currency:

            if currency_client is None:
                conversion_error = (
                    "Currency conversion service was not provided."
                )

            else:
                try:
                    conversion = currency_client.convert(
                        amount=_money(land_total),
                        base_currency=source_currency,
                        target_currency=target_currency,
                    )

                    comparison_total = Decimal(
                        str(conversion["converted_amount"])
                    )

                    comparison_currency = target_currency

                except (
                    ExternalAPIError,
                    ValueError,
                    KeyError,
                    TypeError,
                    InvalidOperation,
                ) as exc:
                    conversion_error = str(exc)

    # Validate the user's budget.
    budget_value: Decimal | None = None

    if budget_amount is not None:

        try:
            budget_value = Decimal(
                str(budget_amount)
            )

        except InvalidOperation as exc:
            raise ValueError(
                "budget_amount must be a valid number"
            ) from exc

        if budget_value < 0:
            raise ValueError(
                "budget_amount cannot be negative"
            )

    price_is_lower_bound = (
        match.get("price_basis")
        == "tier_starting_price_lower_bound"
    )

    budget_status = "not_provided"

    budget_message = (
        "No budget comparison was requested."
    )

    if budget_includes_flights:

        budget_status = (
            "full_budget_not_assessable_flights_excluded"
        )

        budget_message = (
            "This land-trip estimate excludes international "
            "flights. The complete budget cannot be assessed "
            "without an airfare estimate."
        )

    elif budget_value is not None and budget_currency:

        if comparison_currency != budget_currency.upper():

            budget_status = (
                "not_assessable_currency_conversion_failed"
            )

            budget_message = (
                "The land-cost estimate is available, but "
                "the budget comparison could not be completed "
                "because currency conversion failed."
            )

        elif price_is_lower_bound:

            if budget_value < comparison_total:

                budget_status = (
                    "below_published_starting_cost"
                )

                budget_message = (
                    "The budget is below the source's "
                    "published starting-cost estimate. "
                    "Actual costs may be higher."
                )

            else:

                budget_status = (
                    "starting_cost_within_budget_not_confirmed"
                )

                budget_message = (
                    "The budget covers the published starting-cost "
                    "estimate, but the source provides a starting "
                    "price rather than an average or upper range. "
                    "Budget sufficiency is not confirmed."
                )

        else:

            if budget_value >= comparison_total:

                budget_status = (
                    "within_recorded_average_estimate"
                )

                budget_message = (
                    "The budget is at or above the recorded "
                    "average-cost estimate. Actual spending can vary."
                )

            else:

                budget_status = (
                    "below_recorded_average_estimate"
                )

                budget_message = (
                    "The budget is below the recorded average-cost "
                    "estimate. A lower-cost travel style or updated "
                    "research may be needed."
                )

    result = {
        "status": "estimated",
        "destination": match["destination"],
        "country": match["country"],
        "location_level": match["location_level"],
        "price_tier": match["price_tier"],
        "travelers": travelers,
        "duration_days": duration_days,
        "daily_cost_per_person": _money(daily_cost),
        "land_trip_total": _money(land_total),
        "currency": source_currency,
        "comparison_total": _money(comparison_total),
        "comparison_currency": comparison_currency,
        "budget_amount": (
            _money(budget_value)
            if budget_value is not None
            else None
        ),
        "budget_currency": (
            budget_currency.upper()
            if budget_currency
            else None
        ),
        "budget_includes_flights": budget_includes_flights,
        "budget_status": budget_status,
        "budget_message": budget_message,
        "currency_conversion": conversion,
        "currency_conversion_error": conversion_error,
        "source": {
            "name": match["source_name"],
            "url": match["source_url"],
            "license": match["license"],
            "data_version": match["data_version"],
            "price_basis": match["price_basis"],
            "estimate_label": match["estimate_label"],
            "location_level": match["location_level"],
        },
        "assumptions": [
            (
                "The selected daily rate is per traveler and "
                "already includes accommodation, food, local "
                "transport and activities as described by the source."
            ),
            "Accommodation must not be added again as a separate charge.",
            "The estimate is daily rate × travelers × trip days.",
            "International flights, visas and travel insurance are excluded.",
        ],
    }

    if match.get("tier_defaulted_to_mid_range"):
        result["assumptions"].append(
            "No recognized travel-cost tier was supplied; "
            "mid-range was used."
        )

    if price_is_lower_bound:
        result["assumptions"].append(
            "The source provides a published starting price, "
            "not an average or upper bound; actual costs may be higher."
        )
    else:
        result["assumptions"].append(
            "The source provides a recorded average daily cost; "
            "actual spending may vary."
        )

    if match.get("location_level") == "country":
        result["assumptions"].append(
            "The source represents country-level costs, which may "
            "differ from the specific destination city or region."
        )
    elif match.get("location_level") == "region":
        result["assumptions"].append(
            "The source represents regional costs, which may differ "
            "across individual cities and areas."
        )

    return result
