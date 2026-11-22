import asyncio

import httpx
from pydantic import Field
from pydantic_logger import LoggingConfig, LoggingLevel, PydanticBuiltinLogger
from pydantic_settings import BaseSettings, SettingsConfigDict

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

LOGGER = PydanticBuiltinLogger.model_validate({"name": __name__})


class Main(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        cli_parse_args=True,
        cli_kebab_case=True,
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
        LoggingConfig(level=LoggingLevel.INFO).apply()
        seen: set[PriceQuote] = set()
        while True:
            for watch in self.watches:
                for source in self.sources:
                    quotes = await source.fetch_quotes(watch)
                    if isinstance(quotes, Exception):
                        LOGGER.warning("source failed: %s", quotes)
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
                LOGGER.error("notification failed: %s", result)
