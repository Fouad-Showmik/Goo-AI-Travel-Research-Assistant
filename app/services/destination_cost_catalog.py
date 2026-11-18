from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any, ClassVar

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"

TIER_ALIASES = {
    "budget": "budget",
    "economy": "budget",
    "low cost": "budget",
    "low-cost": "budget",
    "backpacker": "budget",
    "mid": "mid_range",
    "mid range": "mid_range",
    "mid-range": "mid_range",
    "midrange": "mid_range",
    "moderate": "mid_range",
    "comfortable": "mid_range",
    "standard": "mid_range",
    "luxury": "luxury",
    "premium": "luxury",
    "upscale": "luxury",
    "high end": "luxury",
    "high-end": "luxury",
}

COUNTRY_ALIASES = {
    "turkey": "turkiye",
    "czech republic": "czechia",
    "usa": "united states",
    "us": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "uae": "united arab emirates",
}

CITY_ALIASES = {
    "saigon": "ho chi minh city",
    "hcmc": "ho chi minh city",
    "nyc": "new york city",
    "new york": "new york city",
    "sao paulo": "são paulo",
    "krakow": "kraków",
    "malaga": "málaga",
    "bogota": "bogotá",
    "medellin": "medellín",
    "cancun": "cancún",
}

#Raised when a destination-cost catalog cannot be loaded or validated.
class DestinationCostCatalogError(Exception):
    pass

#Look up published per-person daily travel budgets from local CSV files.
#City records are checked first. If no city-level match is found,
#a country record may be returned when a country name is known.
class DestinationCostCatalog:
    
    REQUIRED_COLUMNS : ClassVar[dict[str, Any]] ={
        "destination_name",
        "country_name",
        "location_level",
        "currency",
        "budget_daily_per_person",
        "mid_range_daily_per_person",
        "luxury_daily_per_person",
        "unit",
        "price_basis",
        "source_name",
        "source_url",
        "license",
    }

    def __init__(
        self,
        city_csv: str | Path | None = None,
        country_csv: str | Path | None = None,
    ):
        data_dir = DEFAULT_DATA_DIR

        self.city_csv = (
            Path(city_csv)
            if city_csv
            else data_dir / "city_travel_costs.csv"
        )

        self.country_csv = (
            Path(country_csv)
            if country_csv
            else data_dir / "country_travel_costs.csv"
        )

        self._destination_records = self._load_csv(
            self.city_csv,
            expected_level=("city", "region"),
        )

        self._city_records = [
            row for row in self._destination_records
            if row["location_level"] == "city"
        ]

        self._region_records = [
            row for row in self._destination_records
            if row["location_level"] == "region"
        ]

        self._country_records = self._load_csv(
            self.country_csv,
            expected_level="country",
        )

        self._city_index: dict[
            tuple[str, str],
            list[dict[str, str]]
        ] = {}

        self._region_index: dict[
            tuple[str, str],
            list[dict[str, str]]
        ] = {}

        self._country_index: dict[
            str,
            dict[str, str]
        ] = {}

        for row in self._city_records:
            key = (
                self._normalize_city(row["destination_name"]),
                self._normalize_country(row["country_name"]),
            )

            self._city_index.setdefault(key, []).append(row)

        for row in self._region_records:
            key = (
                self._normalize(row["destination_name"]),
                self._normalize_country(row["country_name"]),
            )

            self._region_index.setdefault(key, []).append(row)

        for row in self._country_records:
            key = self._normalize_country(
                row["destination_name"]
            )

            if key in self._country_index:
                raise DestinationCostCatalogError(
                    f"Duplicate country record in "
                    f"{self.country_csv}: "
                    f"{row['destination_name']}"
                )

            self._country_index[key] = row

    @staticmethod
    def _normalize(value: str | None):
        if not value:
            return ""

        normalized = unicodedata.normalize(
            "NFKD",
            value.casefold(),
        )

        normalized = "".join(
            char
            for char in normalized
            if not unicodedata.combining(char)
        )

        normalized = re.sub(
            r"[^a-z0-9]+",
            " ",
            normalized,
        )

        return " ".join(normalized.split())

    @classmethod
    def _normalize_country(cls, value: str | None):
        normalized = cls._normalize(value)

        return COUNTRY_ALIASES.get(
            normalized,
            normalized,
        )

    @classmethod
    def _normalize_city(cls, value: str | None):
        normalized = cls._normalize(value)

        alias = CITY_ALIASES.get(normalized)

        return cls._normalize(alias) if alias else normalized

    #Return canonical tier and whether the default was applied.
    @staticmethod
    def normalize_tier(
        value: str | None,
    ):

        if not value or not value.strip():
            return "mid_range", True

        normalized = (
            value.strip()
            .casefold()
            .replace("_", " ")
        )

        tier = TIER_ALIASES.get(normalized)

        if tier is None:
            # Existing accommodation preferences may describe
            # lodging comfort rather than overall travel spending.
            # Use mid-range transparently in that case.
            return "mid_range", True

        return tier, False

    @classmethod
    def _split_destination(
        cls,
        destination: str,
        country: str | None,
    ):

        destination = destination.strip()

        parsed_country = (
            country.strip()
            if country and country.strip()
            else None
        )

        if "," in destination:
            parts = [
                part.strip()
                for part in destination.split(",")
                if part.strip()
            ]

            if len(parts) >= 2:
                destination = parts[0]

                if parsed_country is None:
                    parsed_country = parts[-1]

        return destination, parsed_country

    def _load_csv(
        self,
        path: Path,
        expected_level: str | tuple[str, ...],
    ):
        expected_levels = (
            {expected_level}
            if isinstance(expected_level, str)
            else set(expected_level)
        )

        if not path.is_file():
            raise DestinationCostCatalogError(
                f"Catalog file not found: {path}"
            )

        try:
            with path.open(
                "r",
                newline="",
                encoding="utf-8-sig",
            ) as handle:

                reader = csv.DictReader(handle)

                fieldnames = set(reader.fieldnames or [])

                missing = self.REQUIRED_COLUMNS - fieldnames

                if missing:
                    raise DestinationCostCatalogError(
                        f"{path.name} is missing columns: "
                        f"{sorted(missing)}"
                    )

                rows: list[dict[str, str]] = []

                for line_number, row in enumerate(
                    reader,
                    start=2,
                ):

                    actual_level = (
                        row.get("location_level") or ""
                    ).strip().lower()

                    if actual_level not in expected_levels:
                        raise DestinationCostCatalogError(
                            f"Unexpected location_level '{actual_level}' "
                            f"at {path.name}:{line_number}. "
                            f"Expected one of: {sorted(expected_levels)}"
                        )

                    row["location_level"] = actual_level

                    if (
                        not row.get("destination_name")
                        or not row.get("currency")
                    ):
                        raise DestinationCostCatalogError(
                            f"Missing destination or currency at "
                            f"{path.name}:{line_number}"
                        )

                    if len(row["currency"].strip()) != 3:
                        raise DestinationCostCatalogError(
                            f"Invalid currency code at "
                            f"{path.name}:{line_number}"
                        )

                    for column in (
                        "budget_daily_per_person",
                        "mid_range_daily_per_person",
                        "luxury_daily_per_person",
                    ):

                        try:
                            value = float(row[column])

                        except (TypeError, ValueError) as exc:
                            raise DestinationCostCatalogError(
                                f"Invalid {column} at "
                                f"{path.name}:{line_number}"
                            ) from exc

                        if value <= 0:
                            raise DestinationCostCatalogError(
                                f"Non-positive {column} at "
                                f"{path.name}:{line_number}"
                            )

                    rows.append(row)

                return rows

        except OSError as exc:
            raise DestinationCostCatalogError(
                f"Unable to read catalog file: {path}"
            ) from exc

    #Return a city match first, then a country match, else None
    def lookup(
        self,
        destination: str,
        price_tier: str | None = None,
        country: str | None = None,
    ):
        
        if not destination or not destination.strip():
            return None

        destination_name, country_name = self._split_destination(
            destination,
            country,
        )

        tier, tier_defaulted = self.normalize_tier(
            price_tier
        )

        tier_column = {
            "budget": "budget_daily_per_person",
            "mid_range": "mid_range_daily_per_person",
            "luxury": "luxury_daily_per_person",
        }[tier]

        city_key = self._normalize_city(destination_name)

        country_key = self._normalize_country(
            country_name
        )

        # Prefer exact city + country match.
        if country_key:
            city_matches = self._city_index.get(
                (city_key, country_key),
                [],
            )

        else:
            city_matches = [
                row
                for (
                    candidate_city,
                    _candidate_country,
                ), records in self._city_index.items()
                if candidate_city == city_key
                for row in records
            ]

        # Do not guess when a city name is ambiguous.
        if len(city_matches) == 1:
            return self._serialize_match(
                city_matches[0],
                tier,
                tier_column,
                tier_defaulted,
            )

        if len(city_matches) > 1:
            return {
                "status": "ambiguous_city",
                "destination": destination_name,
                "candidate_countries": sorted({
                    row["country_name"]
                    for row in city_matches
                }),
                "message": (
                    "A country is required to select "
                    "the correct city record."
                ),
            }

        # No city match: try an exact region match.
        region_key = self._normalize(destination_name)

        if country_key:
            region_matches = self._region_index.get(
                (region_key, country_key),
                [],
            )
        else:
            region_matches = [
                row
                for (
                    candidate_region,
                    _candidate_country,
                ), records in self._region_index.items()
                if candidate_region == region_key
                for row in records
            ]

        if len(region_matches) == 1:
            return self._serialize_match(
                region_matches[0],
                tier,
                tier_column,
                tier_defaulted,
            )

        if len(region_matches) > 1:
            return {
                "status": "ambiguous_region",
                "destination": destination_name,
                "candidate_countries": sorted({
                    row["country_name"]
                    for row in region_matches
                }),
                "message": (
                    "A country is required to select "
                    "the correct region record."
                ),
            }

        # No city found: try the explicitly provided country.
        # If destination itself is a country name, use it.
        country_candidate = country_name or destination_name

        country_row = self._country_index.get(
            self._normalize_country(country_candidate)
        )

        if country_row is not None:
            return self._serialize_match(
                country_row,
                tier,
                tier_column,
                tier_defaulted,
            )

        return None

    @staticmethod
    def _serialize_match(
        row: dict[str, str],
        tier: str,
        tier_column: str,
        tier_defaulted: bool,
    ):

        daily_cost = float(row[tier_column])

        is_starting_price = (
            row["price_basis"]
            == "tier_starting_price_lower_bound"
        )

        return {
            "status": "found",
            "destination": row["destination_name"],
            "country": row["country_name"],
            "location_level": row["location_level"],
            "price_tier": tier,
            "daily_cost_per_person": daily_cost,
            "currency": row["currency"].upper(),
            "unit": row["unit"],
            "price_basis": row["price_basis"],
            "estimate_label": (
                "published starting price"
                if is_starting_price
                else "recorded average daily cost"
            ),
            "tier_defaulted_to_mid_range": tier_defaulted,
            "data_version": row.get("data_version", ""),
            "source_name": row["source_name"],
            "source_url": row["source_url"],
            "license": row["license"],
            "includes": row.get("includes", ""),
            "excludes": row.get("excludes", ""),
            "source_notes": row.get("source_notes", ""),
        }

    @property
    def counts(self):
        return {
            "city_records": len(self._city_records),
            "region_records": len(self._region_records),
            "country_records": len(self._country_records),
        }
