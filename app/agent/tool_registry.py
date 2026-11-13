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
    TravelCostRequest,
    WeatherRequest,
)
from app.tools.currency import convert_currency
from app.tools.destination import search_destination
from app.tools.nearby_places import search_nearby_places
from app.tools.travel_cost import estimate_travel_cost
from app.tools.weather import get_weather

# Maps each exposed tool name to its Python function and input schema.

TOOL_REGISTRY: dict[
    str,
    tuple[Callable[..., dict[str, Any]], type[BaseModel]]
] = {
    "get_weather": (
        get_weather,
        WeatherRequest,
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
def execute_tool(name: str, arguments: dict):
    tool_entry = TOOL_REGISTRY.get(name)

    if tool_entry is None:
        raise ValueError(f"Unknown tool: {name}")

    function, input_schema = tool_entry

    # Validate arguments before executing the Python function.

    validated_arguments = input_schema.model_validate(arguments)

    # Convert the validated Pydantic model back to a dictionary.

    return function(**validated_arguments.model_dump())
