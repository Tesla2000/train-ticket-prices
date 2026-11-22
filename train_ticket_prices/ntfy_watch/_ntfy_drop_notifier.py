from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf, SecretStr

from train_ticket_prices.ntfy_watch._ntfy_topic_reader import NtfyTopicReader
from train_ticket_prices.price_source import PriceQuote, PriceSourceType

DROP_TITLE = "Train price drop"
KOLEO_SEARCH = "https://koleo.pl/rozklad-pkp"
BILKOM_SEARCH = "https://bilkom.pl/podroz"


class NtfyDropNotifier(BaseModel):
    """Posts a drop to ntfy with a link to the source's search page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_url: str = "https://ntfy.sh"
    topic: str
    token: SecretStr | None = None
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )

    async def notify(self, quote: PriceQuote) -> httpx.HTTPError | None:
        headers = NtfyTopicReader.auth_headers(self.token)
        headers["Title"] = DROP_TITLE
        try:
            response = await self.client.post(
                f"{self.server_url}/{self.topic}",
                content=self.message(quote),
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return error
        return None

    @staticmethod
    def message(quote: PriceQuote) -> str:
        return (
            f"{quote.origin.value} -> {quote.destination.value} "
            f"{quote.departure:%d.%m %H:%M} {quote.train_label}: "
            f"{quote.price_pln} PLN ({quote.source.value})\n"
            f"{NtfyDropNotifier.link(quote)}"
        )

    @staticmethod
    def link(quote: PriceQuote) -> str:
        if quote.source == PriceSourceType.KOLEO:
            when = f"{quote.departure:%d-%m-%Y_%H:%M}"
            return (
                f"{KOLEO_SEARCH}/{quote.origin.value}/"
                f"{quote.destination.value}/{when}"
            )
        query = urlencode(
            {
                "poczatkowa": quote.origin.value.replace("-", " ").title(),
                "docelowa": quote.destination.value.replace("-", " ").title(),
                "data": f"{quote.departure:%d%m%Y%H%M}",
            }
        )
        return f"{BILKOM_SEARCH}?{query}"
