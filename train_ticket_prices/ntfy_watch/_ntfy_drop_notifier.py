from collections.abc import Iterable
from logging import Logger, getLogger
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices.price_source import PriceQuote, PriceSourceType

DROP_TITLE = "Train price drop"
KOLEO_SEARCH = "https://koleo.pl/rozklad-pkp"
BILKOM_SEARCH = "https://bilkom.pl/podroz"


class NtfyDropNotifier(BaseModel):
    """Queues drops not yet sent, then posts them to ntfy as one message.

    `sent` holds keys from history; a drop is skipped when its key is in
    `sent` or already queued, so one train listed by two sources is sent once.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_url: str = "https://ntfy.sh"
    topic: str
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )
    sent: frozenset[str] = frozenset()
    pending: list[PriceQuote] = Field(default_factory=list, exclude=True)
    logger: InstanceOf[Logger] = Field(
        exclude=True, default_factory=lambda: getLogger(__name__)
    )

    async def notify(self, quote: PriceQuote) -> None:
        key = self.key(self.message(quote))
        if key in self.sent:
            self.logger.info(
                "skipped, already in history: %s (%s)",
                key,
                quote.source.value,
            )
        elif key in {
            self.key(self.message(queued)) for queued in self.pending
        }:
            self.logger.info(
                "skipped, already listed this run: %s (%s)",
                key,
                quote.source.value,
            )
        else:
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
    def sent_keys(history: Iterable[str]) -> frozenset[str]:
        return frozenset(
            NtfyDropNotifier.key(line)
            for text in history
            for line in text.splitlines()
        )

    @staticmethod
    def key(line: str) -> str:
        """Route and departure only, so a train listed by one source is not repeated by another."""
        return " ".join(line.split()[:5])

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
