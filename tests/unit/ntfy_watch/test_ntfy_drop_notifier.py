from decimal import Decimal

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
async def test_notify_sends_nothing_until_flush() -> None:
    posted: list[httpx.Request] = []
    drop_notifier = notifier(posted=posted)

    await drop_notifier.notify(BILKOM_QUOTE)

    assert posted == []


@pytest.mark.unit
@run_async
async def test_flush_posts_message_with_link_and_title() -> None:
    posted: list[httpx.Request] = []
    drop_notifier = notifier(posted=posted)
    await drop_notifier.notify(BILKOM_QUOTE)

    result = await drop_notifier.flush()

    assert result is None
    assert posted[0].headers["Title"] == "Train price drop"
    assert posted[0].content.decode() == NtfyDropNotifier.message(BILKOM_QUOTE)
    assert "bilkom.pl/podroz?" in posted[0].content.decode()


@pytest.mark.unit
@run_async
async def test_flush_posts_all_queued_drops_as_one_message() -> None:
    posted: list[httpx.Request] = []
    other = QUOTE.model_copy(
        update={"departure": QUOTE.departure.replace(hour=7)}
    )
    drop_notifier = notifier(posted=posted)
    await drop_notifier.notify(QUOTE)
    await drop_notifier.notify(other)

    await drop_notifier.flush()

    assert len(posted) == 1
    assert posted[0].content.decode() == (
        f"{NtfyDropNotifier.message(QUOTE)}\n\n"
        f"{NtfyDropNotifier.message(other)}"
    )


@pytest.mark.unit
@run_async
async def test_flush_without_drops_posts_nothing() -> None:
    posted: list[httpx.Request] = []

    assert await notifier(posted=posted).flush() is None
    assert posted == []


@pytest.mark.unit
@run_async
async def test_flush_returns_http_error_as_value() -> None:
    drop_notifier = notifier(status=500)
    await drop_notifier.notify(QUOTE)

    assert isinstance(await drop_notifier.flush(), httpx.HTTPError)


@pytest.mark.unit
@run_async
async def test_notify_skips_drop_already_in_sent_history() -> None:
    posted: list[httpx.Request] = []
    drop_notifier = notifier(posted=posted).model_copy(
        update={
            "sent": frozenset(
                {NtfyDropNotifier.key(NtfyDropNotifier.message(QUOTE))}
            )
        }
    )

    await drop_notifier.notify(QUOTE)

    assert drop_notifier.pending == []
    assert await drop_notifier.flush() is None
    assert posted == []


@pytest.mark.unit
@run_async
async def test_notify_skips_train_already_queued_from_another_source() -> None:
    drop_notifier = notifier()
    bilkom = QUOTE.model_copy(
        update={"source": PriceSourceType.BILKOM, "price_pln": Decimal(41)}
    )

    await drop_notifier.notify(QUOTE)
    await drop_notifier.notify(bilkom)

    assert drop_notifier.pending == [QUOTE]


@pytest.mark.unit
def test_sent_keys_reads_every_line_of_combined_messages() -> None:
    later = QUOTE.model_copy(
        update={"departure": QUOTE.departure.replace(hour=7)}
    )
    combined = f"{NtfyDropNotifier.message(QUOTE)}\n\n{NtfyDropNotifier.message(later)}"

    keys = NtfyDropNotifier.sent_keys((combined,))

    assert NtfyDropNotifier.key(NtfyDropNotifier.message(QUOTE)) in keys
    assert NtfyDropNotifier.key(NtfyDropNotifier.message(later)) in keys
