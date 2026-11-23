from logging import Logger, getLogger
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf

from train_ticket_prices.notification.ntfy._ntfy_batch_service import (
    NtfyBatchService,
)
from train_ticket_prices.notification.ntfy._ntfy_drop_key_service import (
    NtfyDropKeyService,
)
from train_ticket_prices.notification.ntfy._ntfy_drop_message_service import (
    NtfyDropMessageService,
)
from train_ticket_prices.notification.types import NotificationType
from train_ticket_prices.price_source import PriceQuote


class NtfyNotificationService(BaseModel):
    """Queues drops on notify, posts them to ntfy as plain text on flush.

    `sent` holds keys from history; a drop is skipped when its key is in
    `sent` or already queued, so one train listed by two sources is sent once.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[NotificationType.NTFY] = NotificationType.NTFY
    server_url: str = "https://ntfy.sh"
    topic: str
    title: str = "Train price drop"
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )
    batcher: NtfyBatchService = Field(default_factory=NtfyBatchService)
    keys: NtfyDropKeyService = Field(default_factory=NtfyDropKeyService)
    messages: NtfyDropMessageService = Field(
        default_factory=NtfyDropMessageService
    )
    sent: frozenset[str] = frozenset()
    pending: list[PriceQuote] = Field(default_factory=list, exclude=True)
    logger: InstanceOf[Logger] = Field(
        exclude=True, default_factory=lambda: getLogger(__name__)
    )

    async def notify(self, quote: PriceQuote) -> None:
        key = self.keys.extract_key(self.messages.format_message(quote))
        if key in self.sent:
            self.logger.info(
                "skipped, already in history: %s (%s)",
                key,
                quote.source.value,
            )
        elif key in {
            self.keys.extract_key(self.messages.format_message(queued))
            for queued in self.pending
        }:
            self.logger.info(
                "skipped, already listed this run: %s (%s)",
                key,
                quote.source.value,
            )
        else:
            self.pending.append(quote)

    async def flush(self) -> httpx.HTTPError | None:
        """Posts queued drops in batches under the size limit, then clears the queue."""
        contents = self.batcher.batch_messages(tuple(self.pending))
        self.pending.clear()
        for content in contents:
            try:
                response = await self.client.post(
                    f"{self.server_url}/{self.topic}",
                    content=content,
                    headers={"Title": self.title},
                )
                response.raise_for_status()
            except httpx.HTTPError as error:
                return error
        return None
