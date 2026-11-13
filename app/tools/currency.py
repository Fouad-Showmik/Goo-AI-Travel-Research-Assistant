from app.clients.currency_client import CurrencyClient


# Convert an amount using the latest available reference rate.
def convert_currency(
    amount: float,
    base_currency: str,
    target_currency: str,
):
    return CurrencyClient().convert(
        amount,
        base_currency,
        target_currency,
    )
