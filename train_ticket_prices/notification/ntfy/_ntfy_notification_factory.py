from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from train_ticket_prices.notification.ntfy._ntfy_drop_key_service import (
    NtfyDropKeyService,
)
from train_ticket_prices.notification.ntfy._ntfy_notification_service import (
    NtfyNotificationService,
)


class NtfyNotificationFactory(BaseModel):
    """Builds a ntfy notifier that skips drops already listed in history."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    notifier: NtfyNotificationService
    keys: NtfyDropKeyService = Field(default_factory=NtfyDropKeyService)

    def create(self, history: Iterable[str]) -> NtfyNotificationService:
        sent = frozenset(
            self.keys.extract_key(line)
            for text in history
            for line in text.splitlines()
        )
        return self.notifier.model_copy(update={"sent": sent, "pending": []})
