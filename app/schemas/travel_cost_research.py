from math import isfinite
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


#Validated result of web-based destination cost research.
class DestinationCostResearch(BaseModel):

    model_config = ConfigDict(extra="forbid")

    status: Literal["found", "not_found"]

    destination: str = Field(min_length=2, max_length=200)
    country: str | None

    location_level: Literal[
        "city",
        "region",
        "country",
        "unknown",
    ]

    price_tier: Literal[
        "budget",
        "mid_range",
        "luxury",
    ]

    daily_cost_per_person: float | None

    currency: str | None = Field(
        min_length=3,
        max_length=3,
    )

    unit: Literal[
        "per_person_per_day",
        "unknown",
    ]

    price_basis: Literal[
        "recorded_daily_average",
        "tier_starting_price_lower_bound",
        "unknown",
    ]

    included_components: list[
        Literal[
            "accommodation",
            "food",
            "local_transport",
            "activities",
        ]
    ]

    excluded_items: list[str]

    source_url: str | None
    source_title: str | None
    source_evidence: str | None
    published_date: str | None

    notes: str

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None):
        return value.upper().strip() if value else None

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None):
        if value is None:
            return None

        parsed = urlsplit(value)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be a valid HTTP(S) URL.")

        return value

    @model_validator(mode="after")
    def validate_research_result(self):
        if self.status == "not_found":
            return self

        if (
            self.daily_cost_per_person is None
            or not isfinite(self.daily_cost_per_person)
            or self.daily_cost_per_person <= 0
        ):
            raise ValueError(
                "A found result must contain a positive daily cost."
            )

        if not self.currency:
            raise ValueError(
                "A found result must include its source currency."
            )

        if self.unit != "per_person_per_day":
            raise ValueError(
                "The cost must be explicitly reported per person per day."
            )

        if self.price_basis == "unknown":
            raise ValueError(
                "The source must identify the price basis."
            )

        required_components = {
            "accommodation",
            "food",
            "local_transport",
            "activities",
        }

        if not required_components.issubset(
            set(self.included_components)
        ):
            raise ValueError(
                "The daily cost must cover accommodation, food, "
                "local transport, and activities."
            )

        if not self.source_url or not self.source_title:
            raise ValueError(
                "A found result must include a source URL and title."
            )

        if not self.source_evidence:
            raise ValueError(
                "A found result must include supporting source evidence."
            )

        return self