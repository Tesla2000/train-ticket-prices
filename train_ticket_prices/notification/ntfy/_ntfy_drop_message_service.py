from pydantic import BaseModel, ConfigDict

from train_ticket_prices.price_source import PriceQuote


class NtfyDropMessageService(BaseModel):
    """Formats one drop as the plain-text lines ntfy receives."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    def format_message(self, quote: PriceQuote) -> str:
        return (
            f"{quote.origin.value} -> {quote.destination.value} "
            f"{quote.departure:%d.%m %H:%M} {quote.train_label}: "
            f"{quote.price_pln} PLN ({quote.source.value})\n"
            f"{quote.link()}"
        )
