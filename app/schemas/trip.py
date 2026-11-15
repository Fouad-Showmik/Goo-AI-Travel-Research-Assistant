
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


#Structured travel requirements collected from a user.
class TripRequirements(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    #Travel Locations
    origin: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
        description="Starting city, region, or country.",
    )

    destination: str | None = Field(
        default=None,
        min_length=2,
        max_length=160,
        description="Travel destination. Can be a city, region, or entire country."
    )

    # Travelers and trip duration
    travelers: int | None = Field(
        default=None,
        ge=1,
        le=20,
    )

    duration_days: int | None = Field(
        default=None,
        ge=1,
        le=60,
    )

    # Budget
    budget_amount: float | None = Field(
        default=None,
        gt=0,
        le=1_000_000_000_000,
    )

    budget_currency: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{3}$",
    )

    budget_includes_flights: bool | None = None

    #Travel timing
    travel_date: date | None = None

    travel_month: str | None = Field(
        default=None,
        min_length=3,
        max_length=40,
    )

    #Travel preferences
    interests: list[str] = Field(
        default_factory=list,
        max_length=10,
    )

    accommodation_preference: Literal[
        "budget",
        "moderate",
        "comfortable",
    ] | None = None

    @field_validator(
        "origin",
        "destination",
        "travel_month",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("budget_currency", mode="before")
    @classmethod
    def normalize_currency(cls, value):
        if isinstance(value, str):
            value = value.strip().upper()
            return value or None

        return value

    @field_validator("interests")
    @classmethod
    def normalize_interests(cls, values):
        normalized = []
        seen = set()

        for interest in values:

            interest = interest.strip()

            if not interest:
                continue

            key = interest.casefold()

            if key not in seen:
                normalized.append(interest)
                seen.add(key)
        return normalized
