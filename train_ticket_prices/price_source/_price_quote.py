from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from train_ticket_prices.price_source.types import PriceSourceType
from train_ticket_prices.stations.types import Station


class PriceQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: PriceSourceType
    origin: Station
    destination: Station
    departure: datetime
    train_label: str
    price_pln: Decimal
