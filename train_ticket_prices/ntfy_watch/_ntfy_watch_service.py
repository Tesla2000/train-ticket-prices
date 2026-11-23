from logging import Logger, getLogger

from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices._price_watcher import PriceWatcher
from train_ticket_prices.notification.ntfy import NtfyNotificationFactory
from train_ticket_prices.ntfy_watch._ntfy_topic_reader import (
    NtfySince,
    NtfyTopicReader,
)
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
    notifier_factory: NtfyNotificationFactory
    sources: tuple[AnyPriceSourceService, ...] = Field(
        default_factory=lambda: (
            KoleoPriceSourceService(),
            BilkomPriceSourceService(),
        )
    )
    window: NtfySince = NtfySince("12h")
    logger: InstanceOf[Logger] = Field(
        exclude=True, default_factory=lambda: getLogger(__name__)
    )

    async def run_once(self) -> None:
        alerts = await self.config.load_alerts()
        if isinstance(alerts, Exception):
            self.logger.warning("config unavailable: %s", alerts)
            return
        sent_messages = await self.history.read_messages(self.window)
        if isinstance(sent_messages, Exception):
            self.logger.warning(
                "sent history unavailable, notifying nothing: %s",
                sent_messages,
            )
            return
        await PriceWatcher(
            sources=self.sources,
            notifiers=(self.notifier_factory.create(sent_messages),),
        ).run(alerts)
