# performs deterministic calculations


def estimate_travel_cost(
    days: int,
    nights: int,
    travelers: int,
    accommodation_per_night: float,
    food_per_person_per_day: float,
    transport_per_person_per_day: float,
    activities_per_person_per_day: float,
    currency: str = "USD",
):
    accommodation = nights * accommodation_per_night

    food = days * travelers * food_per_person_per_day

    transport = days * travelers * transport_per_person_per_day

    activities = days * travelers * activities_per_person_per_day

    total = accommodation + food + transport + activities

    return {
        "currency": currency.upper(),
        "travelers": travelers,
        "days": days,
        "nights": nights,
        "breakdown": {
            "accommodation": round(accommodation, 2),
            "food": round(food, 2),
            "transport": round(transport, 2),
            "activities": round(activities, 2),
        },
        "total_estimated_cost": round(total, 2),
        "assumptions": {
            "accommodation_per_night": accommodation_per_night,
            "food_per_person_per_day": food_per_person_per_day,
            "transport_per_person_per_day": transport_per_person_per_day,
            "activities_per_person_per_day": activities_per_person_per_day,
        },
        "note": (
            "This calculation uses supplied cost assumptions. "
            "It does not verify actual market prices."
        ),
    }
