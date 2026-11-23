import asyncio
from logging import Logger, getLogger

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices.models import Watch
from train_ticket_prices.notification import (
    AnyNotificationService,
    ConsoleNotificationService,
)
from train_ticket_prices.price_source import (
    AnyPriceSourceService,
    BilkomPriceSourceService,
    KoleoPriceSourceService,
    PriceQuote,
)


class PriceWatch(BaseModel):
    """Notifies drops below threshold. With interval_seconds None, run() is one pass."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    watches: tuple[Watch, ...] = ()
    sources: tuple[AnyPriceSourceService, ...] = Field(
        default_factory=lambda: (
            KoleoPriceSourceService(),
            BilkomPriceSourceService(),
        )
    )
    notifiers: tuple[AnyNotificationService, ...] = Field(
        default_factory=lambda: (ConsoleNotificationService(),)
    )
    interval_seconds: int | None = None
    logger: InstanceOf[Logger] = Field(
        exclude=True, default_factory=lambda: getLogger(__name__)
    )

    async def run(self) -> None:
        seen: set[PriceQuote] = set()
        while True:
            await self._notify_new_drops(seen)
            if self.interval_seconds is None:
                return
            await asyncio.sleep(self.interval_seconds)

    async def _notify_new_drops(self, seen: set[PriceQuote]) -> None:
        for watch in self.watches:
            for source in self.sources:
                quotes = await source.fetch_quotes(watch)
                if isinstance(quotes, Exception):
                    self.logger.warning("source failed: %s", quotes)
                    continue
                for quote in quotes:
                    if (
                        quote.price_pln < watch.threshold_pln
                        and quote not in seen
                    ):
                        seen.add(quote)
                        await self._notify(quote)

    async def _notify(self, quote: PriceQuote) -> None:
        for notifier in self.notifiers:
            result = await notifier.notify(quote)
            if isinstance(result, httpx.HTTPError):
                self.logger.error("notification failed: %s", result)
