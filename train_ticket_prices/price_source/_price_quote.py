from abc import abstractmethod
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from train_ticket_prices.price_source.types import PriceSourceType
from train_ticket_prices.stations import Station


class PriceQuote(BaseModel):
    """A fare found by one source; each source subclass says where to book it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: PriceSourceType
    origin: Station
    destination: Station
    departure: datetime
    train_label: str
    price_pln: Decimal

    @abstractmethod
    def link(self) -> str:
        """Search page for this route and departure."""
