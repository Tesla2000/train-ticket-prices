from datetime import timedelta
from decimal import Decimal

import httpx
import pytest

from tests.unit.notification.test_notification_services import (
    QUOTE,
    key,
    message,
)
from tests.unit.price_source.fixtures import run_async
from train_ticket_prices.notification.ntfy import (
    NtfyNotificationFactory,
    NtfyNotificationService,
)
from train_ticket_prices.price_source import BilkomPriceQuote, PriceSourceType

DROP_COUNT = 60
MAX_BODY_BYTES = 4000
BILKOM_QUOTE = BilkomPriceQuote.model_validate(
    QUOTE.model_dump() | {"source": PriceSourceType.BILKOM}
)


def notifier(
    status: int = 200, posted: list[httpx.Request] | None = None
) -> NtfyNotificationService:
    def handler(request: httpx.Request) -> httpx.Response:
        if posted is not None:
            posted.append(request)
        return httpx.Response(status)

    return NtfyNotificationService(
        topic="trains",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.unit
def test_koleo_link_points_to_koleo_route_page() -> None:
    assert QUOTE.link() == (
        "https://koleo.pl/rozklad-pkp/warszawa-centralna/krakow-glowny/23-11-2026_06:04"
    )


@pytest.mark.unit
def test_bilkom_link_prefills_stations_and_departure() -> None:
    assert BILKOM_QUOTE.link() == (
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
    assert posted[0].content.decode() == message(BILKOM_QUOTE)
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
        f"{message(QUOTE)}\n{message(other)}"
    )


@pytest.mark.unit
@run_async
async def test_flush_splits_drops_into_bodies_under_the_limit() -> None:
    posted: list[httpx.Request] = []
    drop_notifier = notifier(posted=posted)
    drops = range(DROP_COUNT)
    for minutes in drops:
        await drop_notifier.notify(
            QUOTE.model_copy(
                update={
                    "departure": QUOTE.departure + timedelta(minutes=minutes)
                }
            )
        )

    await drop_notifier.flush()

    bodies = [request.content.decode() for request in posted]
    assert len(bodies) > 1
    assert all(len(body.encode()) <= MAX_BODY_BYTES for body in bodies)
    assert sum(body.count(" PLN (") for body in bodies) == DROP_COUNT


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
        update={"sent": frozenset({key(message(QUOTE))})}
    )

    await drop_notifier.notify(QUOTE)

    assert drop_notifier.pending == []
    assert await drop_notifier.flush() is None
    assert posted == []


@pytest.mark.unit
@run_async
async def test_notify_skips_train_already_queued_from_another_source() -> None:
    drop_notifier = notifier()
    bilkom = BilkomPriceQuote.model_validate(
        QUOTE.model_dump()
        | {"source": PriceSourceType.BILKOM, "price_pln": Decimal(41)}
    )

    await drop_notifier.notify(QUOTE)
    await drop_notifier.notify(bilkom)

    assert drop_notifier.pending == [QUOTE]


@pytest.mark.unit
def test_history_skips_every_line_of_combined_messages() -> None:
    later = QUOTE.model_copy(
        update={"departure": QUOTE.departure.replace(hour=7)}
    )
    combined = f"{message(QUOTE)}\n{message(later)}"

    drop_notifier = NtfyNotificationFactory(notifier=notifier()).create(
        (combined,)
    )

    assert key(message(QUOTE)) in drop_notifier.sent
    assert key(message(later)) in drop_notifier.sent
