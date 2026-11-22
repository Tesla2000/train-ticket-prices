import httpx
import pytest

from tests.unit.notification.test_notification_services import QUOTE
from tests.unit.price_source.fixtures import run_async
from train_ticket_prices.ntfy_watch._ntfy_drop_notifier import NtfyDropNotifier
from train_ticket_prices.price_source import PriceQuote, PriceSourceType

BILKOM_QUOTE = PriceQuote.model_validate(
    QUOTE.model_dump() | {"source": PriceSourceType.BILKOM}
)


def notifier(
    status: int = 200, posted: list[httpx.Request] | None = None
) -> NtfyDropNotifier:
    def handler(request: httpx.Request) -> httpx.Response:
        if posted is not None:
            posted.append(request)
        return httpx.Response(status)

    return NtfyDropNotifier(
        topic="trains",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.unit
def test_koleo_link_points_to_koleo_route_page() -> None:
    assert NtfyDropNotifier.link(QUOTE) == (
        "https://koleo.pl/rozklad-pkp/warszawa-centralna/krakow-glowny/23-11-2026_06:04"
    )


@pytest.mark.unit
def test_bilkom_link_prefills_stations_and_departure() -> None:
    assert NtfyDropNotifier.link(BILKOM_QUOTE) == (
        "https://bilkom.pl/podroz?poczatkowa=Warszawa+Centralna"
        "&docelowa=Krakow+Glowny&data=231120260604"
    )


@pytest.mark.unit
@run_async
async def test_notify_posts_message_with_link_and_title() -> None:
    posted: list[httpx.Request] = []

    result = await notifier(posted=posted).notify(BILKOM_QUOTE)

    assert result is None
    assert posted[0].headers["Title"] == "Train price drop"
    assert posted[0].content.decode() == NtfyDropNotifier.message(BILKOM_QUOTE)
    assert "bilkom.pl/podroz?" in posted[0].content.decode()


@pytest.mark.unit
@run_async
async def test_notify_returns_http_error_as_value() -> None:
    assert isinstance(
        await notifier(status=500).notify(QUOTE), httpx.HTTPError
    )
