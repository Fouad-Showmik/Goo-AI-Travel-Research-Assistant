from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from threading import RLock
from time import monotonic
from typing import Any, ClassVar

import requests

from app.clients.errors import ExternalAPIError

logger = logging.getLogger(__name__)


class CurrencyClient:
    """Frankfurter v2 reference-rate client with a small process cache."""

    BASE_URL = "https://api.frankfurter.dev/v2/rate"
    CACHE_TTL_SECONDS = 12 * 60 * 60
    MAX_CACHE_ENTRIES = 256

    _cache: ClassVar[
        dict[tuple[str, str], tuple[float, Decimal, str | None]]
    ] = {}

    _lock: ClassVar[Any] = RLock()

    def _get_rate(self, base: str, target: str) -> tuple[Decimal, str | None]:
        key = (base, target)
        now = monotonic()

        with self._lock:
            cached = self._cache.get(key)

            if cached and now - cached[0] < self.CACHE_TTL_SECONDS:
                return cached[1], cached[2]

        try:
            response = requests.get(
                f"{self.BASE_URL}/{base.lower()}/{target.lower()}",
                timeout=12,
            )
            response.raise_for_status()

            data: dict[str, Any] = response.json()
            rate = Decimal(str(data["rate"]))
            rate_date = data.get("date")

            if not rate.is_finite() or rate <= 0:
                raise ValueError("Exchange rate must be positive and finite.")

        except (
            requests.RequestException,
            KeyError,
            TypeError,
            ValueError,
            InvalidOperation,
        ) as exc:
            logger.exception(
                "Frankfurter v2 currency lookup failed: %s/%s",
                base,
                target,
            )
            raise ExternalAPIError(
                f"Exchange rate for {base} to {target} is unavailable."
            ) from exc

        with self._lock:
            self._cache[key] = (monotonic(), rate, rate_date)

            if len(self._cache) > self.MAX_CACHE_ENTRIES:
                oldest_key = min(
                    self._cache,
                    key=lambda item: self._cache[item][0],
                )
                self._cache.pop(oldest_key, None)

        return rate, rate_date

    def convert(
        self,
        amount: float | str,
        base_currency: str,
        target_currency: str,
    ) -> dict[str, Any]:

        base = base_currency.upper().strip()
        target = target_currency.upper().strip()

        if len(base) != 3 or len(target) != 3:
            raise ValueError("Currencies must be three-letter ISO codes.")

        try:
            decimal_amount = Decimal(str(amount))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Amount must be numeric.") from exc

        if not decimal_amount.is_finite() or decimal_amount < 0:
            raise ValueError("Amount must be finite and non-negative.")

        if base == target:
            rate = Decimal(1)
            rate_date = None
        else:
            rate, rate_date = self._get_rate(base, target)

        converted = (decimal_amount * rate).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        return {
            "amount": float(decimal_amount),
            "base_currency": base,
            "target_currency": target,
            "exchange_rate": float(rate),
            "converted_amount": float(converted),
            "rate_date": rate_date,
            "source": "Frankfurter v2 reference rates",
        }