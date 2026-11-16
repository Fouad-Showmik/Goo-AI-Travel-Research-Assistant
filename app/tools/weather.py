from app.clients.weather_client import WeatherClient


#Return a daily weather forecast for a city.
def get_weather(city: str, forecast_days: int = 5):
    return WeatherClient().get_forecast(city, forecast_days)

# Return historical seasonal weather information for a destination.
def get_seasonal_climate(city: str, travel_month: str):
    return WeatherClient().get_seasonal_climate(city=city, travel_month=travel_month)