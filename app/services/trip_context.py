#Business logic for managing structured trip requirements.

from typing import ClassVar

from app.services.session_store import SessionStore


class TripContextService:
    # Information needed before application begin a basic trip plan.
    REQUIRED_FIELDS: ClassVar[dict[str, str]] = {
        "origin": "starting location",
        "destination": "destination",
        "travelers": "number of travelers",
        "duration_days": "trip duration",
    }

    # Additional information needed for budget evaluation.
    BUDGET_FIELDS: ClassVar[dict[str, str]] = {
        "budget_amount": "total travel budget",
        "budget_currency": "budget currency",
    }

    def __init__(self, store: SessionStore):
        self.store = store

    def get(self, session_id: str):
        return self.store.get_trip_context(session_id)

    def update(self, session_id: str, updates: dict):
        filtered_updates = {
            field: value
            for field, value in updates.items()
            if value is not None
        }

        return self.store.update_trip_context(
            session_id,
            filtered_updates,
        )

    def get_missing_required_fields(self, session_id: str):
        trip = self.get(session_id)

        return [
            description
            for field, description in self.REQUIRED_FIELDS.items()
            if getattr(trip, field) is None
        ]

    def get_missing_budget_fields(self, session_id: str):
        trip = self.get(session_id)

        return [
            description
            for field, description in self.BUDGET_FIELDS.items()
            if getattr(trip, field) is None
        ]

    def can_start_planning(self, session_id: str):
        return not self.get_missing_required_fields(session_id)

    def can_evaluate_budget(self, session_id: str):
        return (
            self.can_start_planning(session_id)
            and not self.get_missing_budget_fields(session_id)
        )

    def clear(self, session_id: str):
        self.store.clear_trip_context(session_id)
