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
            "travel_style": {
                "type": ["string", "null"],
                "enum": [
                    "budget",
                    "mid_range",
                    "luxury",
                    None,
                ],
                "description": (
                    "Overall trip spending preference. "
                    "Use budget for economical travel, mid_range for "
                    "moderate spending, and luxury for premium travel. "
                    "Do not confuse this with accommodation preference."
                ),
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
            "travel_style",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}

ESTIMATE_TRAVEL_COST_TOOL = {
    "type": "function",
    "name": "estimate_travel_cost",

    "description": (
        "Estimate trip costs using the local destination cost catalog first. "
        "The catalog checks city-level records before country-level records. "
        "If no suitable record exists, the tool automatically performs "
        "validated live web research for the requested price tier. "
        "Provide the destination, trip duration, and number of travelers. "
        "Use budget, mid_range, or luxury for the user's travel style. "
        "Use null when travel style is unspecified so the backend can "
        "apply the default mid-range tier. "
        "Provide the country when available for destination identification. "
        "Use the supplied budget amount and currency for budget comparison. "
        "The result includes the estimated cost, source information, "
        "assumptions, and budget comparison. "
        "Never invent unsupported prices or cost assumptions."
    ),

    "parameters": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": (
                    "Destination city, region, or country, "
                    "e.g. Bangkok or Thailand."
                ),
            },
            "days": {
                "type": "integer",
                "minimum": 1,
                "maximum": 60,
                "description": "Total trip duration in days.",
            },
            "travelers": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "Number of travelers.",
            },
            "price_tier": {
                "type": ["string", "null"],
                "enum": ["budget", "mid_range", "luxury", None],
                "description": (
                    "Overall travel spending tier. "
                    "Use budget, mid_range, or luxury. "
                    "Use null when not specified."
                ),
            },
            "country": {
                "type": ["string", "null"],
                "description": (
                    "Country containing the destination, "
                    "when known or needed for disambiguation."
                ),
            },
            "budget_amount": {
                "type": ["number", "null"],
                "minimum": 0,
                "description": "User's total trip budget, if provided.",
            },
            "budget_currency": {
                "type": ["string", "null"],
                "minLength": 3,
                "maxLength": 3,
                "description": (
                    "Three-letter ISO currency code, "
                    "such as BDT, USD, or THB."
                ),
            },
            "budget_includes_flights": {
                "type": "boolean",
                "description": (
                    "Whether the user's stated budget includes flights."
                ),
            },
        },
        "required": [
            "destination",
            "days",
            "travelers",
            "price_tier",
            "country",
            "budget_amount",
            "budget_currency",
            "budget_includes_flights",
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
            "Use religious_site for Buddhist temples, Shinto shrines, "
            "and other religious places. "
            "Use historical_site for castles, archaeological sites, "
            "monuments, memorials, and historical monasteries. "
            "Use all_attractions for general sightseeing."
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
    ESTIMATE_TRAVEL_COST_TOOL,
]
