import asyncio
from logging import Logger, getLogger

import httpx
from pydantic import Field, InstanceOf
from pydantic_logger import LoggingConfig, LoggingLevel
from pydantic_settings import BaseSettings, CliSuppress, SettingsConfigDict

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


class Main(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        cli_parse_args=True,
        cli_kebab_case=True,
    )

    logging: LoggingConfig = Field(
        default_factory=lambda: LoggingConfig(level=LoggingLevel.INFO)
    )
    logger: CliSuppress[InstanceOf[Logger]] = Field(
        exclude=True, default_factory=lambda: getLogger(__name__)
    )
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

    async def cli_cmd(self) -> None:
        self.logging.apply()
        seen: set[PriceQuote] = set()
        while True:
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
            if self.interval_seconds is None:
                return
            await asyncio.sleep(self.interval_seconds)

    async def _notify(self, quote: PriceQuote) -> None:
        for notifier in self.notifiers:
            result = await notifier.notify(quote)
            if isinstance(result, httpx.HTTPError):
                self.logger.error("notification failed: %s", result)
