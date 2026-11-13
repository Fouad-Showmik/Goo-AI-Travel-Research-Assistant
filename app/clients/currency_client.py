import logging

import requests

from app.clients.errors import ExternalAPIError

logger = logging.getLogger(__name__)

class CurrencyClient:
    BASE_URL = "https://api.frankfurter.app/latest"

    def convert(self, amount: float, base_currency: str, target_cuurency: str):
        base = base_currency.upper()
        target = target_cuurency.upper()

        if base == target:
            return {
                "amount": amount,
                "base_currency": base,
                "target_currency": target,
                "exchange_rate": 1.0,
                "converted_amount": round(amount, 2),
                "rate_date": None,
                "source": "Frankfurter",
            }

        try:
            response = requests.get(
                self.BASE_URL,
                params={
                    "from": base,
                    "to": target,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            rate = data.get("rates",{}).get(target)


            if rate is None:
                raise ExternalAPIError(
                    f"Exchange rate for {base} to {target} is unavailable."
                )

            return{
                "amount": amount,
                "base_currency": base,
                "target_currency": target,
                "exchange_rate": rate,
                "converted_amount": round(amount * rate, 2),
                "rate_date": data.get("date"),
                "source": "Frankfurter", 
            }

        except ExternalAPIError:
            raise

        except requests.RequestException as exc:
            logger.exception("Currency API request failed")
            raise ExternalAPIError(
                "Currency conversion is temporarily unavailable."
            ) from exc
