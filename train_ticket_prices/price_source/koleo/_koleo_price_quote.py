from typing import Literal

from train_ticket_prices.price_source._price_quote import PriceQuote
from train_ticket_prices.price_source.types import PriceSourceType

KOLEO_SEARCH = "https://koleo.pl/rozklad-pkp"


class KoleoPriceQuote(PriceQuote):
    source: Literal[PriceSourceType.KOLEO] = PriceSourceType.KOLEO

    def link(self) -> str:
        when = f"{self.departure:%d-%m-%Y_%H:%M}"
        return (
            f"{KOLEO_SEARCH}/{self.origin.value}/"
            f"{self.destination.value}/{when}"
        )
