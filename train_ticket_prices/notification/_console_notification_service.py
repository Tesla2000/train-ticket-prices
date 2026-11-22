from logging import Logger, getLogger
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices.notification.types import NotificationType
from train_ticket_prices.price_source import PriceQuote


class ConsoleNotificationService(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[NotificationType.CONSOLE] = NotificationType.CONSOLE
    logger: InstanceOf[Logger] = Field(
        exclude=True, default_factory=lambda: getLogger(__name__)
    )

    async def notify(self, quote: PriceQuote) -> None:
        self.logger.info(
            "price drop %s -> %s %s %s PLN (%s)",
            quote.origin.value,
            quote.destination.value,
            quote.departure,
            quote.price_pln,
            quote.source.value,
        )
