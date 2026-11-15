# Keeps each visitor's recent messages in memory. Lost on restart.
import threading
import time
from collections.abc import Mapping
from typing import Any

from app.core.config import settings
from app.schemas.trip import TripRequirements


class SessionStore:
    def __init__(self, first_exchanges: int, recent_exchanges: int, ttl_seconds: int):
        if first_exchanges < 0 or recent_exchanges<0:
            raise ValueError("Exchange limits cannot be negative.")
        
        if ttl_seconds <= 0:
            raise ValueError("Session TTL must be positive.")

        self.first_exchanges = first_exchanges
        self.recent_exchanges = recent_exchanges
        self.ttl_seconds = ttl_seconds
        self.sessions : dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()  # requests run in parallel thread

    def _new_session(self):
        return {
            "first": [],
            "recent": [],
            "trip_context": {},
            "last_seen": time.time(),
        }

    #Return an existing session or create a new one.

    def _get_or_create_session(self, session_id: str):
        session = self.sessions.get(session_id)

        if session is None:
            session = self._new_session()
            self.sessions[session_id] = session
        return session

    #Return preserved conversation history.
    def get(self, session_id: str):
        with self.lock:
            self._remove_expired()
            session = self.sessions.get(session_id)

            if not session:
                return []

            session["last_seen"] = time.time()

            # Preserve the first exchanges and latest exchanges.
            exchanges = (
                session["first"] + session["recent"]
            )

            # Flatten exchanges into a single message list.
            messages = []

            for exchange in exchanges:
                messages.extend(
                    dict(message) for message in exchange
                )
            return messages


        
    def save_exchange(self, session_id: str, user_message: str, reply: str):
        with self.lock:
            self._remove_expired()

            session = self._get_or_create_session(session_id)

            # Store each user-assistant pair as one exchange.
            exchange = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": reply},
            ]
            # Preserve the first N exchanges permanently.
            if len(session["first"]) < self.first_exchanges:
                session["first"].append(exchange)

            # Keep the latest N exchanges in a rolling window.
            elif self.recent_exchanges > 0:
                session["recent"].append(exchange)

                if len(session["recent"]) > self.recent_exchanges:
                    session["recent"].pop(0)

            session["last_seen"] = time.time()

    #Retrieve structured trip requirements.
    def get_trip_context(self, session_id: str):
        with self.lock:
            self._remove_expired()

            session = self.sessions.get(session_id)

            if not session:
                return TripRequirements()

            session["last_seen"] = time.time()

            return TripRequirements.model_validate(
                session.get("trip_context", {})
            )


    #Merge new trip information with existing requirements.
    #Omitted and None-valued fields are preserved.
    #Explicit empty lists can replace existing lists.

    def update_trip_context(self, session_id: str, updates: TripRequirements | Mapping[str, Any]):
        if isinstance(updates, TripRequirements):
            changes = updates.model_dump(
                exclude_unset=True,
                exclude_none=True,
                mode="json",
            )
        else:
            validated = TripRequirements.model_validate(updates)

            changes = validated.model_dump(
                exclude_unset=True,
                exclude_none=True,
                mode="json",
            )

        with self.lock:
            self._remove_expired()

            session = self._get_or_create_session(session_id)

            merged = dict(session["trip_context"])
            merged.update(changes)

            updated = TripRequirements.model_validate(merged)
            session["trip_context"] = updated.model_dump(
                exclude_none=True,
                mode="json"
            )

            session["last_seen"] = time.time()

            return updated

    def clear_trip_context(self, session_id: str):
        with self.lock:
            self._remove_expired()

            session = self.sessions.get(session_id)

            if session:
                session["trip_context"] = {}
                session["last_seen"] = time.time()

    #Clear the complete session.

    def clear(self, session_id: str):
        with self.lock:
            self.sessions.pop(session_id, None)


    #Remove sessions exceeding their TTL.
    def _remove_expired(self):

        now = time.time()
        expired = [
            sid
            for sid, s in self.sessions.items()
            if now - s["last_seen"] > self.ttl_seconds
        ]
        for sid in expired:
            del self.sessions[sid]


# One shared instance, so memory survives between requests.
session_store = SessionStore(
    first_exchanges=settings.history_first_exchanges,
    recent_exchanges=settings.history_recent_exchanges,
    ttl_seconds=settings.session_ttl_seconds,
)
