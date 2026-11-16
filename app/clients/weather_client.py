import calendar
import logging
import re
from datetime import date
from statistics import fmean
from typing import Any, ClassVar

import requests

from app.clients.errors import ExternalAPIError

logger = logging.getLogger(__name__)

class WeatherClient:
    GEOCODING_URL = (
        "https://geocoding-api.open-meteo.com/v1/search"
    )
    FORECAST_URL = (
        "https://api.open-meteo.com/v1/forecast"
    )
    HISTORICAL_URL = (
        "https://archive-api.open-meteo.com/v1/archive"
    )

    HISTORICAL_SAMPLE_YEARS: ClassVar[int] = 5

    MONTHS: ClassVar[dict[str, int]] = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }

    #Safely retrieve a value from an Open-Meteo daily series.
    @staticmethod
    def _get_series_value(
        daily: dict[str, Any],
        key: str,
        index: int,
    ):

        values =daily.get(key) or []

        if index >= len(values):
            return None

        return values[index]

    #Resolve a city or region into geographic coordinates.
    def _geocode_city(self, city: str):
        response = requests.get(
            self.GEOCODING_URL,
            params={
            "name": city,
            "count": 1,
            "language": "en",
            "format": "json",
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()
        locations = data.get("results") or []

        if not locations:
            raise ExternalAPIError(
                f"Could not find a location matching '{city}'."
            )
        
        location = locations[0]

        if (
            "latitude" not in location
            or "longitude" not in location
        ):
            raise ExternalAPIError(
                "The resolved weather location has no coordinates."
            )

        return location

    #Convert a month name or month value into an integer.
    @staticmethod
    def _parse_month_number(travel_month: str):

        value = travel_month.strip().casefold()

        # Accept numeric months such as "7".
        if re.fullmatch(r"\d{1,2}", value):
            month_number = int(value)

            if 1 <= month_number <= 12:
                return month_number

        # Accept values such as "2027-07".
        match = re.fullmatch(r"\d{4}[-/](\d{1,2})", value)

        if match:
            month_number = int(match.group(1))

            if 1 <= month_number <= 12:
                return month_number

        # Accept month names such as "July 2027".
        words = re.findall(r"[a-z]+", value)

        for word in words:
            if word in WeatherClient.MONTHS:
                return WeatherClient.MONTHS[word]

        raise ValueError(
            "Provide a valid travel month, such as July or 2027-07."
        )

    #Return a short-term daily weather forecast.
    def get_forecast(
        self,
        city: str,
        forecast_days: int = 5,
    ):
        if not (1 <= forecast_days <= 7):
            raise ValueError(
                "Forecast days must be between 1 and 7."
            )

        try:
            location = self._geocode_city(city)

            forecast_response = requests.get(
                self.FORECAST_URL,
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "daily": (
                        "weather_code,"
                        "temperature_2m_max,"
                        "temperature_2m_min,"
                        "precipitation_probability_max,"
                        "precipitation_sum,"
                        "wind_speed_10m_max"
                    ),
                    "timezone": "auto",
                    "forecast_days": forecast_days,
                },
                timeout=15,
            )

            forecast_response.raise_for_status()

            data = forecast_response.json()
            daily = data.get("daily") or {}

            forecasts = []

            for index, forecast_date in enumerate(
                daily.get("time", [])
            ):
                forecasts.append({
                    "date": forecast_date,
                    "weather_code": self._get_series_value(
                        daily, "weather_code", index
                    ),
                    "temperature_max_c": self._get_series_value(
                        daily, "temperature_2m_max", index
                    ),
                    "temperature_min_c": self._get_series_value(
                        daily, "temperature_2m_min", index
                    ),
                    "precipitation_probability_max_percent": (
                        self._get_series_value(
                            daily,
                            "precipitation_probability_max",
                            index,
                        )
                    ),
                    "precipitation_sum_mm": self._get_series_value(
                        daily, "precipitation_sum", index
                    ),
                    "wind_speed_max_kmh": self._get_series_value(
                        daily, "wind_speed_10m_max", index
                    ),
                })

            return {
                "location": {
                    "name": location.get("name"),
                    "country": location.get("country"),
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "timezone": location.get("timezone"),
                },
                "forecast_days": len(forecasts),
                "forecast": forecasts,
                "source": "Open-Meteo Forecast API",
                "attribution": "Weather data by Open-Meteo.com",
                "attribution_url": "https://open-meteo.com/",
                "license": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
            }

        except ExternalAPIError:
            raise

        except (
            requests.RequestException,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            logger.exception("Weather forecast request failed")

            raise ExternalAPIError(
                "Weather information is temporarily unavailable."
            ) from exc


    #Return historical weather patterns for a travel month.
    #Uses the previous five complete calendar years.
    #This is historical seasonal information, not a forecast.

    def get_seasonal_climate(
        self,
        city: str,
        travel_month: str,
    ):
        try:
            month_number = self._parse_month_number(travel_month)

            # Use complete historical calendar years only.
            end_year = date.today().year - 1

            start_year = (
                end_year - self.HISTORICAL_SAMPLE_YEARS + 1
            )

            start_date = f"{start_year}-01-01"
            end_date = f"{end_year}-12-31"

            location = self._geocode_city(city)

            response = requests.get(
                self.HISTORICAL_URL,
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "start_date": start_date,
                    "end_date": end_date,
                    "daily": (
                        "temperature_2m_max,"
                        "temperature_2m_min,"
                        "precipitation_sum"
                    ),
                    "timezone": "auto",
                },
                timeout=(10, 45),
            )

            response.raise_for_status()

            data = response.json()
            daily = data.get("daily") or {}

            dates = daily.get("time") or []

            if not dates:
                raise ExternalAPIError(
                    "No historical weather data was returned."
                )

            daily_highs = []
            daily_lows = []

            # Keep precipitation statistics separately for each year.
            monthly_statistics: dict[int, dict[str, Any]] = {}

            sample_days = 0

            for index, date_string in enumerate(dates):

                observation_date = date.fromisoformat(date_string)

                # Select only the requested calendar month.
                if observation_date.month != month_number:
                    continue

                sample_days += 1

                year = observation_date.year

                statistics = monthly_statistics.setdefault(
                    year,
                    {
                        "precipitation_total": 0.0,
                        "precipitation_days": 0,
                        "rainy_days": 0,
                    },
                )

                high = self._get_series_value(
                    daily,
                    "temperature_2m_max",
                    index,
                )

                low = self._get_series_value(
                    daily,
                    "temperature_2m_min",
                    index,
                )

                precipitation = self._get_series_value(
                    daily,
                    "precipitation_sum",
                    index,
                )

                if high is not None:
                    daily_highs.append(float(high))

                if low is not None:
                    daily_lows.append(float(low))

                if precipitation is not None:
                    precipitation = float(precipitation)

                    statistics["precipitation_total"] += precipitation
                    statistics["precipitation_days"] += 1

                    # Define a rainy day as at least 1 mm of precipitation.
                    if precipitation >= 1.0:
                        statistics["rainy_days"] += 1

            if not daily_highs or not daily_lows:
                raise ExternalAPIError(
                    "Insufficient historical temperature data."
                )

            # Only use complete months when calculating average
            # monthly precipitation and rainy-day counts.
            complete_months = []

            for year, statistics in monthly_statistics.items():

                expected_days = calendar.monthrange(
                    year,
                    month_number,
                )[1]

                if statistics["precipitation_days"] == expected_days:
                    complete_months.append(statistics)

            if not complete_months:
                raise ExternalAPIError(
                    "Insufficient historical precipitation data."
                )

            average_monthly_precipitation = fmean(
                item["precipitation_total"]
                for item in complete_months
            )

            average_rainy_days = fmean(
                item["rainy_days"]
                for item in complete_months
            )

            sampled_years = sorted(monthly_statistics.keys())

            return {
                "location": {
                    "name": location.get("name"),
                    "country": location.get("country"),
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "timezone": location.get("timezone"),
                },
                "historical_seasonal_pattern": {
                    "travel_month": calendar.month_name[month_number],
                    "average_daily_high_c": round(
                        fmean(daily_highs), 1
                    ),
                    "average_daily_low_c": round(
                        fmean(daily_lows), 1
                    ),
                    "average_monthly_precipitation_mm": round(
                        average_monthly_precipitation, 1
                    ),
                    "average_rainy_days_per_month": round(
                        average_rainy_days, 1
                    ),
                    "rainy_day_threshold_mm": 1.0,
                },
                "historical_period": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "years_sampled": sampled_years,
                    "complete_precipitation_years": len(
                        complete_months
                    ),
                    "sample_days": sample_days,
                },
                "interpretation_note": (
                    "These figures summarize historical observations "
                    "for the requested month across the previous five "
                    "complete calendar years. They describe a historical "
                    "seasonal pattern, not a future weather forecast or "
                    "an official 30-year climate normal."
                ),
                "source": "Open-Meteo Historical Weather API",
                "attribution": "Weather data by Open-Meteo.com",
                "attribution_url": "https://open-meteo.com/",
                "license": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
            }

        except ExternalAPIError:
            raise

        except (
            requests.RequestException,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            logger.exception("Seasonal climate request failed")

            raise ExternalAPIError(
                "Historical seasonal weather information is "
                "temporarily unavailable."
            ) from exc