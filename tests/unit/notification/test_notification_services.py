from datetime import datetime
from decimal import Decimal

import pytest

from tests.unit.price_source.fixtures import WARSAW, run_async
from train_ticket_prices.notification import ConsoleNotificationService
from train_ticket_prices.notification.ntfy import (
    NtfyDropKeyService,
    NtfyDropMessageService,
)
from train_ticket_prices.price_source import KoleoPriceQuote, PriceSourceType
from train_ticket_prices.stations import Station

QUOTE = KoleoPriceQuote(
    source=PriceSourceType.KOLEO,
    origin=Station.WARSZAWA_CENTRALNA,
    destination=Station.KRAKOW_GLOWNY,
    departure=datetime(2026, 11, 23, 6, 4, tzinfo=WARSAW),
    train_label="IC 1320",
    price_pln=Decimal("45.5"),
)


# Formatting lives in NtfyDropMessageService; these aliases let tests pin it.
key = NtfyDropKeyService().extract_key
message = NtfyDropMessageService().format_message


@pytest.mark.unit
@run_async
async def test_console_notification_logs_quote() -> None:
    assert await ConsoleNotificationService().notify(QUOTE) is None


@pytest.mark.unit
@run_async
async def test_console_flush_has_nothing_to_send() -> None:
    assert await ConsoleNotificationService().flush() is None
