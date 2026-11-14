# Keeps each visitor's recent messages in memory. Lost on restart.
import threading
import time

from app.core.config import settings


class SessionStore:
    def __init__(self, first_exchanges: int, recent_exchanges: int, ttl_seconds: int):
        self.first_exchanges = first_exchanges
        self.recent_exchanges = recent_exchanges
        self.ttl_seconds = ttl_seconds
        self.sessions = {}
        self.lock = threading.Lock()  # requests run in parallel thread

    def get(self, session_id: str):
        with self.lock:
            self._remove_expired()
            session = self.sessions.get(session_id)

            if not session:
                return []

            # Preserve the first exchanges and latest exchanges.
            exchanges = (
                session["first"] + session["recent"]
            )

            # Flatten exchanges into a single message list.
            messages = []

            for exchange in exchanges:
                messages.extend(exchange)
            return messages
        
    def save_exchange(self, session_id: str, user_message: str, reply: str):
        with self.lock:
            self._remove_expired()
            session = self.sessions.setdefault(
                session_id, 
                {
                    "first": [],
                    "recent": [],
                    "last_seen": time.time(),
                },
            )

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

    def clear(self, session_id: str):
        with self.lock:
            self.sessions.pop(session_id, None)

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
