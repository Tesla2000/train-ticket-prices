import asyncio
from itertools import product
from logging import Logger, getLogger

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf, PrivateAttr

from train_ticket_prices.models import PriceAlert
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


class PriceWatcher(BaseModel):
    """Notifies drops below threshold. With interval_seconds None, run() is one pass."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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
    _seen: set[PriceQuote] = PrivateAttr(default_factory=set)

    async def run(self, alerts: tuple[PriceAlert, ...]) -> None:
        self._seen.clear()
        while True:
            await self._notify_new_drops(alerts)
            await self._flush()
            if self.interval_seconds is None:
                return
            await asyncio.sleep(self.interval_seconds)

    async def _notify_new_drops(self, alerts: tuple[PriceAlert, ...]) -> None:
        for alert, source in product(alerts, self.sources):
            quotes = await source.fetch_quotes(alert)
            if isinstance(quotes, Exception):
                self.logger.warning("source failed: %s", quotes)
                continue
            await self._notify_below_threshold(alert, quotes)

    async def _notify_below_threshold(
        self, alert: PriceAlert, quotes: tuple[PriceQuote, ...]
    ) -> None:
        for quote in quotes:
            if (
                quote.price_pln < alert.threshold_pln
                and quote not in self._seen
            ):
                self._seen.add(quote)
                await self._notify(quote)

    async def _notify(self, quote: PriceQuote) -> None:
        for notifier in self.notifiers:
            await notifier.notify(quote)

    async def _flush(self) -> None:
        for notifier in self.notifiers:
            result = await notifier.flush()
            if isinstance(result, httpx.HTTPError):
                self.logger.error("notification failed: %s", result)
