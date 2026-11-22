from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices.notification.types import NotificationType
from train_ticket_prices.price_source import PriceQuote


class NtfyNotificationService(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[NotificationType.NTFY] = NotificationType.NTFY
    server_url: str = "https://ntfy.sh"
    topic: str
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )

    async def notify(self, quote: PriceQuote) -> httpx.HTTPError | None:
        try:
            response = await self.client.post(
                f"{self.server_url}/{self.topic}",
                content=self._message(quote),
                headers={"Title": "Train price drop"},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return error
        return None

    @staticmethod
    def _message(quote: PriceQuote) -> str:
        return (
            f"{quote.origin.value} -> {quote.destination.value} "
            f"{quote.departure:%d.%m %H:%M} {quote.train_label}: "
            f"{quote.price_pln} PLN ({quote.source.value})"
        )
