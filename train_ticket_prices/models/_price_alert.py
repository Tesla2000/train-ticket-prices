from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from train_ticket_prices.models._departure_range import DepartureRange
from train_ticket_prices.stations import Station


class PriceAlert(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Station
    destination: Station
    departure: DepartureRange
    threshold_pln: Decimal
