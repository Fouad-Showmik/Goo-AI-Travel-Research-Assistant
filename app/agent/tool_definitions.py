#Following JSON Schema descriptions help the model(LLM Provider) 
#To understand when each tool should be used.


from typing import get_args

from app.schemas.tools import PlaceCategory

# Available categories are taken from the existing Pydantic schema.
PLACE_CATEGORIES = list(get_args(PlaceCategory))

UPDATE_TRIP_REQUIREMENTS_TOOL = {
    "type": "function",
    "name": "update_trip_requirements",
    "description": (
        "Save or update travel requirements explicitly provided by "
        "the user during the conversation. Call this when the user "
        "provides or corrects trip details. Use null for fields that "
        "are unknown or not being updated. Null values will be ignored. "
        "Use an empty interests array only when the user explicitly "
        "wants to clear previously saved interests."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "origin": {
                "type": ["string", "null"],
                "description": "Starting city, region, or country.",
            },
            "destination": {
                "type": ["string", "null"],
                "description": "Destination city, region, or entire country.",
            },
            "travelers": {
                "type": ["integer", "null"],
                "description": "Number of travelers.",
            },
            "duration_days": {
                "type": ["integer", "null"],
                "description": "Trip duration in days.",
            },
            "budget_amount": {
                "type": ["number", "null"],
                "description": "Total travel budget amount.",
            },
            "budget_currency": {
                "type": ["string", "null"],
                "description": "Three-letter ISO currency code, such as BDT, USD, or THB.",
            },
            "budget_includes_flights": {
                "type": ["boolean", "null"],
                "description": "Whether the stated budget includes flight costs.",
            },
            "travel_date": {
                "type": ["string", "null"],
                "description": "Travel start date in YYYY-MM-DD format.",
            },
            "travel_month": {
                "type": ["string", "null"],
                "description": "Intended travel month or month and year.",
            },
            "interests": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Explicitly stated travel interests.",
            },
            "accommodation_preference": {
                "type": ["string", "null"],
                "enum": [
                    "budget",
                    "moderate",
                    "comfortable",
                    None,
                ],
                "description": "Preferred accommodation comfort level.",
            },
        },
        "required": [
            "origin",
            "destination",
            "travelers",
            "duration_days",
            "budget_amount",
            "budget_currency",
            "budget_includes_flights",
            "travel_date",
            "travel_month",
            "interests",
            "accommodation_preference",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}

TOOL_DEFINITIONS = [
    UPDATE_TRIP_REQUIREMENTS_TOOL,
    {
        "type": "function",
        "name": "get_weather",
        "description": (
            "Retrieve a daily weather forecast for a city. "
            "Use this when the user asks about weather or upcoming "
            "weather conditions at a destination."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City and country, e.g. Bangkok, Thailand.",
                },
                "forecast_days": {
                    "type": "integer",
                    "description": "Number of forecast days. Use 5 by default; allowed range is 1 to 7.",
                },
            },
            "required": ["city", "forecast_days"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_seasonal_climate",
        "description": (
            "Retrieve historical seasonal weather information for a "
            "destination and travel month. Use this when the user asks "
            "about typical weather, temperature, rainfall, or seasonal "
            "conditions for a future trip month or a period outside the "
            "short-term forecast horizon. The result summarizes the "
            "previous five complete calendar years. It is historical "
            "information, not a future weather forecast or an official "
            "30-year climate normal. Provide a specific city or region, "
            "not an entire country."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": (
                        "Specific destination city or region with its country, "
                        "e.g. Bangkok, Thailand."
                    ),
                },
                "travel_month": {
                    "type": "string",
                    "description": ("Travel month, e.g. July, July 2027, or 2027-07."),
                },
            },
            "required": [
                "city",
                "travel_month",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "convert_currency",
        "description": (
            "Convert an amount between two currencies using the latest "
            "available reference exchange rate. Use ISO 4217 currency "
            "codes, such as USD, EUR, BDT, or THB."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount to convert.",
                },
                "base_currency": {
                    "type": "string",
                    "description": "Three-letter source currency code.",
                },
                "target_currency": {
                    "type": "string",
                    "description": "Three-letter destination currency code.",
                },
            },
            "required": [
                "amount",
                "base_currency",
                "target_currency",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_destination",
        "description": (
            "Search for a destination, city, landmark, or geographic "
            "location and retrieve matching location details and coordinates. "
            "Use this when the user wants to identify or locate a destination."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Destination or location search query.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum matching locations. Use 5 by default; allowed range is 1 to 10.",
                },
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_nearby_places",
        "description": (
            "Search for attractions, restaurants, museums, hotels, "
            "and other supported places. City and region destinations "
            "use radius-based OpenStreetMap Overpass searches. Entire "
            "countries use Geoapify Places API bounding-box searches "
            "with results filtered against the actual country boundary. "
            "Country-level results are limited and are not exhaustive. "
            "Country-wide searches support sightseeing, not "
            "restaurants, cafes, or hotels."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location with city and country, e.g. Kyoto, Japan.",
                },
                "category": {
                    "type": "string",
                    "enum": PLACE_CATEGORIES,
                    "description": "Type of places to search for. Use all_attractions for a broad sightseeing overview.",
                },
                "radius": {
                    "type": "integer",
                    "description": "Search radius in meters. Use 5000 by default; allowed range is 100 to 10000.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of places. Use 20 by default; allowed range is 1 to 50.",
                },
            },
            "required": [
                "location",
                "category",
                "radius",
                "limit",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "estimate_travel_cost",
        "description": (
            "Calculate a deterministic travel budget from cost assumptions "
            "provided by the user. Accommodation cost is the total group "
            "cost per night. Food, transport, and activity costs are per "
            "person per day. Do not invent market prices or cost assumptions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of travel days.",
                },
                "nights": {
                    "type": "integer",
                    "description": "Number of accommodation nights.",
                },
                "travelers": {
                    "type": "integer",
                    "description": "Number of travelers.",
                },
                "accommodation_per_night": {
                    "type": "number",
                    "description": "Total accommodation cost for the group per night.",
                },
                "food_per_person_per_day": {
                    "type": "number",
                    "description": "Food cost per traveler per day.",
                },
                "transport_per_person_per_day": {
                    "type": "number",
                    "description": "Transport cost per traveler per day.",
                },
                "activities_per_person_per_day": {
                    "type": "number",
                    "description": "Activities cost per traveler per day.",
                },
                "currency": {
                    "type": "string",
                    "description": "Three-letter currency code. Use USD by default.",
                },
            },
            "required": [
                "days",
                "nights",
                "travelers",
                "accommodation_per_night",
                "food_per_person_per_day",
                "transport_per_person_per_day",
                "activities_per_person_per_day",
                "currency",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
]
