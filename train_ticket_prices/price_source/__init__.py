from typing import Annotated

from pydantic import Field

from train_ticket_prices.price_source._bilkom_price_source_service import (
    BilkomPriceSourceService as BilkomPriceSourceService,
)
from train_ticket_prices.price_source._koleo_price_source_service import (
    KoleoPriceSourceService as KoleoPriceSourceService,
)
from train_ticket_prices.price_source._price_quote import (
    PriceQuote as PriceQuote,
)
from train_ticket_prices.price_source.types import (
    PriceSourceType as PriceSourceType,
)

AnyPriceSourceService = Annotated[
    BilkomPriceSourceService | KoleoPriceSourceService,
    Field(discriminator="type"),
]

__all__ = [
    "AnyPriceSourceService",
    "BilkomPriceSourceService",
    "KoleoPriceSourceService",
    "PriceQuote",
    "PriceSourceType",
]
