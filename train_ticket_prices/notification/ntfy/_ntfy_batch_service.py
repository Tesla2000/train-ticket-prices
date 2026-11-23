from pydantic import BaseModel, ConfigDict, Field

from train_ticket_prices.notification.ntfy._ntfy_drop_message_service import (
    NtfyDropMessageService,
)
from train_ticket_prices.price_source import PriceQuote


class NtfyBatchService(BaseModel):
    """Joins drops into ntfy message bodies under the size limit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ntfy turns longer message bodies into an attachment instead of plain text.
    max_body_bytes: int = 4000
    messages: NtfyDropMessageService = Field(
        default_factory=NtfyDropMessageService
    )
    separator: str = "\n"

    def batch_messages(
        self, quotes: tuple[PriceQuote, ...]
    ) -> tuple[str, ...]:
        """Joins drops into bodies of at most max_body_bytes, so ntfy keeps them as text."""
        batches: list[str] = []
        for quote in quotes:
            text = self.messages.format_message(quote)
            if (
                batches
                and len(f"{batches[-1]}{self.separator}{text}".encode())
                <= self.max_body_bytes
            ):
                batches[-1] = f"{batches[-1]}{self.separator}{text}"
            else:
                batches.append(text)
        return tuple(batches)
