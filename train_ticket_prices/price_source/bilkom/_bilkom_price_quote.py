from typing import Literal
from urllib.parse import urlencode

from train_ticket_prices.price_source._price_quote import PriceQuote
from train_ticket_prices.price_source.types import PriceSourceType

BILKOM_SEARCH = "https://bilkom.pl/podroz"


class BilkomPriceQuote(PriceQuote):
    source: Literal[PriceSourceType.BILKOM] = PriceSourceType.BILKOM

    def link(self) -> str:
        query = urlencode(
            {
                "poczatkowa": self.origin.value.replace("-", " ").title(),
                "docelowa": self.destination.value.replace("-", " ").title(),
                "data": f"{self.departure:%d%m%Y%H%M}",
            }
        )
        return f"{BILKOM_SEARCH}?{query}"
