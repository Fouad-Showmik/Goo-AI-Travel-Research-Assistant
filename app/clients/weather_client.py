import logging

import requests

from app.clients.errors import ExternalAPIError

logger = logging.getLogger(__name__)

class WeatherClient:
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def get_forecast(self, city: str, forecast_days: int = 5):
        try:
            location_response = requests.get(self.GEOCODING_URL, params={
                "name":city,
                "count": 1,
                "language":"en",
                "format":"json",
            },
            timeout=15,
            )

            location_response.raise_for_status()

            locations = location_response.json().get("results",[])

            if not locations:
                raise ExternalAPIError(
                    f"Could not find a location matching '{city}'."
                )
            location = locations[0]

            forecast_response = requests.get(
                self.FORECAST_URL,
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "daily": (
                        "weather_code,"
                        "temperature_2m_max,"
                        "temperature_2m_min,"
                        "precipitation_probability_max"
                    ),
                    "timezone": "auto",
                    "forecast_days": forecast_days,
                },
                timeout=15,
            )
            forecast_response.raise_for_status()
            daily = forecast_response.json().get("daily", {})

            forecasts = []

            for index, date in enumerate(daily.get("time", [])):
                forecasts.append({
                    "date": date,
                    "weather_code": daily["weather_code"][index],
                    "temperature_max_c": daily["temperature_2m_max"][index],
                    "temperature_min_c": daily["temperature_2m_min"][index],
                    "precipitation_probability_max_percent":
                        daily["precipitation_probability_max"][index],
                })

            return {
                    "location": {
                    "name": location.get("name"),
                    "country": location.get("country"),
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "timezone": location.get("timezone"),
                },
                "forecast": forecasts,
                "source": "Open-Meteo",
            }
        
        except ExternalAPIError:
            raise

        except (requests.RequestException, KeyError, ValueError) as exc:
            logger.exception("Weather API request failed")
            raise ExternalAPIError(
                "Weather information is temporarily unavailable"
            ) from exc