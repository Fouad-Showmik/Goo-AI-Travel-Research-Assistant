#Pydantic data validation for the tools.
from typing import Literal

from pydantic import BaseModel, Field

# Supported nearby-place categories
PlaceCategory = Literal[
    "restaurant",
    "cafe",
    "hotel",
    "attraction",
    "all_attractions",
    "museum",
    "viewpoint",
    "historical_site",
    "beach",
    "waterfall",
    "park",
    "picnic_site",
    "camp_site",
    "zoo",
    "aquarium",
    "theme_park",
    "gallery",
    "artwork",
]

class WeatherRequest(BaseModel):
    city: str = Field(min_length=2, max_length=100)
    forecast_days: int = Field(default=5, ge=1, le=7)

class SeasonalClimateRequest(BaseModel):
    city: str = Field(
        min_length=2,
        max_length=100,
    )

    travel_month: str = Field(
        min_length=3,
        max_length=30,
        description=(
            "Travel month, e.g. July, July 2027, or 2027-07."
        ),
    )

class CurrencyRequest(BaseModel):
    amount: float = Field(gt=0, le=1_000_000_000)
    base_currency: str = Field(min_length=3, max_length=3)
    target_currency: str = Field(min_length=3, max_length=3)

class DestinationSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)

class NearbyPlacesRequest(BaseModel):
    location: str = Field(min_length=2, max_length=200)
    category: PlaceCategory
    radius: int = Field(default=5000, ge=100, le=10000)
    limit: int = Field(default=20, ge=1, le=50)

class TravelCostRequest(BaseModel):
    days: int = Field(ge=1, le=60)
    nights: int = Field(ge=0, le=60)
    travelers: int = Field(ge=1, le=20)

    accommodation_per_night: float = Field(ge=0)
    food_per_person_per_day: float = Field(ge=0)
    transport_per_person_per_day: float = Field(ge=0)
    activities_per_person_per_day: float = Field(ge=0)

    currency: str = Field(default="USD", min_length=3, max_length=3)