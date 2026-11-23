from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices.price_source import PriceQuote, PriceSourceType

DROP_TITLE = "Train price drop"
KOLEO_SEARCH = "https://koleo.pl/rozklad-pkp"
BILKOM_SEARCH = "https://bilkom.pl/podroz"


class NtfyDropNotifier(BaseModel):
    """Posts a drop to ntfy with a link to the source's search page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_url: str = "https://ntfy.sh"
    topic: str
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )
    pending: list[PriceQuote] = Field(default_factory=list, exclude=True)

    def notify(self, quote: PriceQuote) -> None:
        """Queues a drop; nothing is sent until flush."""
        self.pending.append(quote)

    async def flush(self) -> httpx.HTTPError | None:
        """Posts all queued drops as a single message."""
        if not self.pending:
            return None
        content = self.batch_message(tuple(self.pending))
        self.pending.clear()
        try:
            response = await self.client.post(
                f"{self.server_url}/{self.topic}",
                content=content,
                headers={"Title": DROP_TITLE},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return error
        return None

    @staticmethod
    def batch_message(quotes: tuple[PriceQuote, ...]) -> str:
        return "\n\n".join(NtfyDropNotifier.message(quote) for quote in quotes)

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
