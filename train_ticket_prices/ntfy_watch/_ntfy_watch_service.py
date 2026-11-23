from logging import Logger, getLogger

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices.models import Watch
from train_ticket_prices.ntfy_watch._ntfy_drop_notifier import NtfyDropNotifier
from train_ticket_prices.ntfy_watch._ntfy_topic_reader import NtfyTopicReader
from train_ticket_prices.ntfy_watch._ntfy_watch_config_service import (
    NtfyWatchConfigService,
)
from train_ticket_prices.price_source import (
    AnyPriceSourceService,
    BilkomPriceSourceService,
    KoleoPriceSourceService,
    PriceQuote,
)


class NtfyWatchService(BaseModel):
    """One check run: config from ntfy, drops not yet sent in the window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config: NtfyWatchConfigService
    history: NtfyTopicReader
    notifier: NtfyDropNotifier
    sources: tuple[AnyPriceSourceService, ...] = Field(
        default_factory=lambda: (
            KoleoPriceSourceService(),
            BilkomPriceSourceService(),
        )
    )
    window: str = "12h"
    logger: InstanceOf[Logger] = Field(
        exclude=True, default_factory=lambda: getLogger(__name__)
    )

    async def run_once(self) -> None:
        watches = await self.config.watches()
        if isinstance(watches, Exception):
            self.logger.warning("config unavailable: %s", watches)
            return
        sent = await self.history.messages(self.window)
        if isinstance(sent, Exception):
            self.logger.warning(
                "sent history unavailable, notifying nothing: %s", sent
            )
            return
        sent_keys = {
            self.key(line) for text in sent for line in text.splitlines()
        }
        seen: set[str] = set()
        drops: list[PriceQuote] = []
        for watch in watches:
            for source in self.sources:
                quotes = await source.fetch_quotes(watch)
                if isinstance(quotes, Exception):
                    self.logger.warning("source failed: %s", quotes)
                    continue
                drops += self._new_drops(watch, quotes, sent_keys, seen)
        result = await self.notifier.flush(tuple(drops))
        if isinstance(result, httpx.HTTPError):
            self.logger.error("notification failed: %s", result)

    def _new_drops(
        self,
        watch: Watch,
        quotes: tuple[PriceQuote, ...],
        sent_keys: set[str],
        seen: set[str],
    ) -> list[PriceQuote]:
        drops: list[PriceQuote] = []
        for quote in quotes:
            if quote.price_pln >= watch.threshold_pln:
                continue
            key = self.key(self.notifier.message(quote))
            if key in sent_keys:
                self.logger.info(
                    "skipped, already in history: %s (%s)",
                    key,
                    quote.source.value,
                )
            elif key in seen:
                self.logger.info(
                    "skipped, already listed this run: %s (%s)",
                    key,
                    quote.source.value,
                )
            else:
                seen.add(key)
                drops.append(quote)
        return drops

    @staticmethod
    def key(line: str) -> str:
        """Route and departure only, so a train listed by one source is not repeated by another."""
        return " ".join(line.split()[:5])
