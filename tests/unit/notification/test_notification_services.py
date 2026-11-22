from datetime import datetime
from decimal import Decimal

import httpx
import pytest

from tests.unit.price_source.fixtures import WARSAW, run_async
from train_ticket_prices.notification import (
    ConsoleNotificationService,
    NtfyNotificationService,
)
from train_ticket_prices.price_source import PriceQuote, PriceSourceType
from train_ticket_prices.stations.types import Station

QUOTE = PriceQuote(
    source=PriceSourceType.KOLEO,
    origin=Station.WARSZAWA_CENTRALNA,
    destination=Station.KRAKOW_GLOWNY,
    departure=datetime(2026, 11, 23, 6, 4, tzinfo=WARSAW),
    train_label="IC 1320",
    price_pln=Decimal("45.5"),
)


@pytest.mark.unit
@run_async
async def test_ntfy_posts_message_to_topic() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    service = NtfyNotificationService(
        topic="trains",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await service.notify(QUOTE)

    assert result is None
    assert str(requests[0].url) == "https://ntfy.sh/trains"
    assert requests[0].headers["Title"] == "Train price drop"
    assert b"IC 1320" in requests[0].content


@pytest.mark.unit
@run_async
async def test_ntfy_failure_is_returned_as_value() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    service = NtfyNotificationService(
        topic="trains",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert isinstance(await service.notify(QUOTE), httpx.HTTPError)


@pytest.mark.unit
@run_async
async def test_console_notification_logs_quote() -> None:
    assert await ConsoleNotificationService().notify(QUOTE) is None
