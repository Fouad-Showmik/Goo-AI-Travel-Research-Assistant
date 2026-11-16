from fastapi import APIRouter, HTTPException, Request

from app.clients.errors import ExternalAPIError
from app.core.limiter import limiter
from app.schemas.tools import (
    CurrencyRequest,
    DestinationSearchRequest,
    NearbyPlacesRequest,
    SeasonalClimateRequest,
    TravelCostRequest,
    WeatherRequest,
)
from app.tools.currency import convert_currency
from app.tools.destination import search_destination
from app.tools.nearby_places import search_nearby_places
from app.tools.travel_cost import estimate_travel_cost
from app.tools.weather import get_seasonal_climate, get_weather

router = APIRouter(
    prefix="/api/tools",
    tags=["information-tools"]
)

@router.post("/weather")
@limiter.limit("10/minute")

def weather_endpoint(request: Request, body: WeatherRequest):
    try:
        return get_weather(
            body.city,
            body.forecast_days,
        )

    except ExternalAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.post("/seasonal-climate")
@limiter.limit("10/minute")

def seasonal_climate_endpoint(request: Request, body: SeasonalClimateRequest):
    try:
        return get_seasonal_climate(
            city=body.city,
            travel_month=body.travel_month,
        )
    except ExternalAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    

@router.post("/currency")
@limiter.limit("10/minute")

def currency_endpoint(request: Request, body: CurrencyRequest):
    try:
        return convert_currency(
            body.amount,
            body.base_currency,
            body.target_currency,
        )
    except ExternalAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.post("/places")
@limiter.limit("10/minute")
def destination_endpoint(request: Request, body: DestinationSearchRequest):
    try:
        return search_destination(
            body.query,
            body.limit,
        )
    except ExternalAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.post("/nearby-places")
@limiter.limit("10/minute")
def nearby_places_endpoint(request: Request, body: NearbyPlacesRequest):
    try:
        return search_nearby_places(
            location=body.location,
            category=body.category,
            radius=body.radius,
            limit=body.limit,
        )
    except ExternalAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/travel-cost")
@limiter.limit("10/minute")
def travel_cost_endppoint(request: Request, body: TravelCostRequest):
    return estimate_travel_cost(**body.model_dump())
    