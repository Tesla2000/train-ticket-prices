from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_logger import PydanticBuiltinLogger

from train_ticket_prices.notification.types import NotificationType
from train_ticket_prices.price_source import PriceQuote

LOGGER = PydanticBuiltinLogger.model_validate({"name": __name__})


class ConsoleNotificationService(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[NotificationType.CONSOLE] = NotificationType.CONSOLE

    async def notify(self, quote: PriceQuote) -> None:
        LOGGER.info(
            "price drop %s -> %s %s %s PLN (%s)",
            quote.origin.value,
            quote.destination.value,
            quote.departure,
            quote.price_pln,
            quote.source.value,
        )
