#Update the structured travel requirements for a session.
from typing import Any

from app.services.trip_context import TripContextService


def update_trip_requirements(session_id: str, updates: dict[str, Any], trip_context_service: TripContextService):
    updated = trip_context_service.update(session_id, updates)

    return {
        "updated_fields": list(updates.keys()),
        "trip_requirements": updated.model_dump(mode="json"),
        "missing_required_fields": (trip_context_service.get_missing_required_fields(session_id)),
        "missing_budget_fields": (
            trip_context_service.get_missing_budget_fields(session_id)
        ),
        "can_start_planning": (trip_context_service.can_start_planning(session_id)),
        "can_evaluate_budget": (trip_context_service.can_evaluate_budget(session_id)),
    }