#The registry identifies which actual Python function should execute 
#when the model selects a tool.
#The Model can only execute the explicitly registered functions in tool_registry.

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.schemas.tools import (
    CurrencyRequest,
    DestinationSearchRequest,
    NearbyPlacesRequest,
    SeasonalClimateRequest,
    TravelCostRequest,
    WeatherRequest,
)
from app.schemas.trip import TripRequirements
from app.tools.currency import convert_currency
from app.tools.destination import search_destination
from app.tools.nearby_places import search_nearby_places
from app.tools.travel_cost import estimate_travel_cost
from app.tools.trip import update_trip_requirements
from app.tools.weather import get_seasonal_climate, get_weather

# Maps each exposed tool name to its Python function and input schema.

TOOL_REGISTRY: dict[
    str,
    tuple[Callable[..., dict[str, Any]], type[BaseModel]]
] = {
    "update_trip_requirements": (
        update_trip_requirements,
        TripRequirements,
    ),
    "get_weather": (
        get_weather,
        WeatherRequest,
    ),
    "get_seasonal_climate": (
        get_seasonal_climate,
        SeasonalClimateRequest,
    ),
    "convert_currency": (
        convert_currency,
        CurrencyRequest,
    ),
    "search_destination": (
        search_destination,
        DestinationSearchRequest,
    ),
    "search_nearby_places": (
        search_nearby_places,
        NearbyPlacesRequest,
    ),
    "estimate_travel_cost": (
        estimate_travel_cost,
        TravelCostRequest,
    ),
}


#Validate arguments and execute the requested registered tool.
def execute_tool(name: str, arguments: dict, context: dict[str, Any] | None = None):
    tool_entry = TOOL_REGISTRY.get(name)

    if tool_entry is None:
        raise ValueError(f"Unknown tool: {name}")

    function, input_schema = tool_entry

    # Null values mean that the LLM has no new information
    # for those fields. Do not overwrite saved values with None.
    if name == "update_trip_requirements":
        arguments = {
            key: value
            for key, value in arguments.items()
            if value is not None
        }

    # Validate arguments before executing the Python function.

    validated_arguments = input_schema.model_validate(arguments)

    if name == "update_trip_requirements":
        if not context:
            raise RuntimeError("Trip context is unavailable.")
        session_id = context.get("session_id")
        trip_context_service = context.get("trip_context_service")

        if not session_id or trip_context_service is None:
            raise RuntimeError("Required trip context information is missing.")

        updates = validated_arguments.model_dump(
            exclude_unset=True,
            exclude_none=True,
            mode="json",
        )

        return function(
            session_id=session_id,
            updates=updates,
            trip_context_service=trip_context_service,
        )
    # Convert the validated Pydantic model back to a dictionary.

    return function(**validated_arguments.model_dump())
