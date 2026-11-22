from typing import Annotated

from pydantic import Field

from train_ticket_prices.notification._console_notification_service import (
    ConsoleNotificationService as ConsoleNotificationService,
)
from train_ticket_prices.notification._ntfy_notification_service import (
    NtfyNotificationService as NtfyNotificationService,
)

AnyNotificationService = Annotated[
    ConsoleNotificationService | NtfyNotificationService,
    Field(discriminator="type"),
]

__all__ = [
    "AnyNotificationService",
    "ConsoleNotificationService",
    "NtfyNotificationService",
]
