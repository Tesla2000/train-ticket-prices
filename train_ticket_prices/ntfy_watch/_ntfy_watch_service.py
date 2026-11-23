from logging import Logger, getLogger

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices._main import Main
from train_ticket_prices.ntfy_watch._ntfy_drop_notifier import NtfyDropNotifier
from train_ticket_prices.ntfy_watch._ntfy_topic_reader import NtfyTopicReader
from train_ticket_prices.ntfy_watch._ntfy_watch_config_service import (
    NtfyWatchConfigService,
)
from train_ticket_prices.price_source import (
    AnyPriceSourceService,
    BilkomPriceSourceService,
    KoleoPriceSourceService,
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
        notifier = self.notifier.model_copy(
            update={"sent": NtfyDropNotifier.sent_keys(sent), "pending": []}
        )
        await Main.model_construct(
            watches=watches, sources=self.sources, notifiers=(notifier,)
        ).check(set())
        result = await notifier.flush()
        if isinstance(result, httpx.HTTPError):
            self.logger.error("notification failed: %s", result)
