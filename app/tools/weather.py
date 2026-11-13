from app.clients.weather_client import WeatherClient


#Return a daily weather forecast for a city.
def get_weather(city: str, forecast_days: int = 5):
    return WeatherClient().get_forecast(city, forecast_days)