from typing import Annotated

from pydantic import Field

from train_ticket_prices.price_source._price_quote import (
    PriceQuote as PriceQuote,
)
from train_ticket_prices.price_source.bilkom import (
    BilkomPriceQuote as BilkomPriceQuote,
)
from train_ticket_prices.price_source.bilkom import (
    BilkomPriceSourceService as BilkomPriceSourceService,
)
from train_ticket_prices.price_source.koleo import (
    KoleoPriceQuote as KoleoPriceQuote,
)
from train_ticket_prices.price_source.koleo import (
    KoleoPriceSourceService as KoleoPriceSourceService,
)
from train_ticket_prices.price_source.types import (
    PriceSourceType as PriceSourceType,
)

AnyPriceSourceService = Annotated[
    BilkomPriceSourceService | KoleoPriceSourceService,
    Field(discriminator="type"),
]
AnyPriceQuote = Annotated[
    BilkomPriceQuote | KoleoPriceQuote,
    Field(discriminator="source"),
]

__all__ = [
    "AnyPriceQuote",
    "AnyPriceSourceService",
    "BilkomPriceQuote",
    "BilkomPriceSourceService",
    "KoleoPriceQuote",
    "KoleoPriceSourceService",
    "PriceQuote",
    "PriceSourceType",
]
