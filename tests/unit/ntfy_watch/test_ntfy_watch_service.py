import json
from decimal import Decimal

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, InstanceOf

from tests.unit.notification.test_notification_services import QUOTE, message
from tests.unit.price_source.fixtures import run_async
from train_ticket_prices.models import PriceAlert
from train_ticket_prices.notification.ntfy import (
    NtfyNotificationFactory,
    NtfyNotificationService,
)
from train_ticket_prices.ntfy_watch import (
    NtfySince,
    NtfyTopicReader,
    NtfyWatchConfigService,
    NtfyWatchService,
)
from train_ticket_prices.price_source import (
    BilkomPriceQuote,
    KoleoPriceQuote,
    KoleoPriceSourceService,
    PriceSourceType,
)

CONFIG_LINE = (
    "warszawa-centralna->krakow-glowny;2026-11-23T06:00->2026-11-23T12:00;50"
)
EXPENSIVE = QUOTE.model_copy(update={"price_pln": Decimal(90)})


class FakeSource(KoleoPriceSourceService):
    result: object

    async def fetch_quotes(self, _alert: PriceAlert) -> object:
        return self.result


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    config: str = CONFIG_LINE
    history: tuple[str, ...] = ()
    sources: tuple[InstanceOf[FakeSource], ...] = (
        FakeSource(result=(QUOTE,)),
    )
    read_status: int = 200
    history_read_status: int = 200
    post_status: int = 200


async def run(scenario: Scenario | None = None) -> list[httpx.Request]:
    scenario = scenario or Scenario()
    posted: list[httpx.Request] = []
    events = [{"event": "message", "message": scenario.config}]
    events += [
        {"event": "message", "message": text} for text in scenario.history
    ]
    body = "\n".join(json.dumps(event) for event in events)

    reads: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(request)
            return httpx.Response(scenario.post_status)
        reads.append(1)
        if len(reads) == 2:  # noqa: PLR2004
            return httpx.Response(scenario.history_read_status, text=body)
        return httpx.Response(scenario.read_status, text=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = NtfyWatchService.model_construct(
        config=NtfyWatchConfigService(
            reader=NtfyTopicReader(topic="trains", client=client)
        ),
        history=NtfyTopicReader(topic="trains", client=client),
        notifier_factory=NtfyNotificationFactory(
            notifier=NtfyNotificationService(topic="trains", client=client)
        ),
        sources=scenario.sources,
        window=NtfySince("12h"),
    )
    await service.run_once()
    return posted


def bodies(requests: list[httpx.Request]) -> list[str]:
    return [request.content.decode() for request in requests]


@pytest.mark.unit
@run_async
async def test_posts_drop_below_threshold() -> None:
    posted = await run()

    assert bodies(posted) == [message(QUOTE)]


@pytest.mark.unit
@run_async
async def test_all_new_drops_of_a_run_are_sent_in_one_message() -> None:
    later = QUOTE.model_copy(
        update={"departure": QUOTE.departure.replace(hour=7)}
    )

    posted = await run(Scenario(sources=(FakeSource(result=(QUOTE, later)),)))

    combined = f"{message(QUOTE)}\n{message(later)}"

    assert bodies(posted) == [combined]


@pytest.mark.unit
@run_async
async def test_drops_listed_in_combined_history_are_not_sent_again() -> None:
    later = QUOTE.model_copy(
        update={"departure": QUOTE.departure.replace(hour=7)}
    )
    combined = f"{message(QUOTE)}\n{message(later)}"

    posted = await run(
        Scenario(
            history=(combined,), sources=(FakeSource(result=(QUOTE, later)),)
        )
    )

    assert posted == []


@pytest.mark.unit
@run_async
async def test_only_undelivered_drops_are_sent_when_history_has_some() -> None:
    later = QUOTE.model_copy(
        update={"departure": QUOTE.departure.replace(hour=7)}
    )

    posted = await run(
        Scenario(
            history=(message(QUOTE),),
            sources=(FakeSource(result=(QUOTE, later)),),
        )
    )

    assert bodies(posted) == [message(later)]


@pytest.mark.unit
@run_async
async def test_price_at_or_above_threshold_is_not_sent() -> None:
    assert (
        await run(Scenario(sources=(FakeSource(result=(EXPENSIVE,)),))) == []
    )


@pytest.mark.unit
@run_async
async def test_drop_already_in_history_is_not_sent_again() -> None:
    posted = await run(Scenario(history=(message(QUOTE),)))

    assert posted == []


@pytest.mark.unit
@run_async
async def test_same_drop_from_two_sources_is_sent_once() -> None:
    posted = await run(
        Scenario(
            sources=(FakeSource(result=(QUOTE,)), FakeSource(result=(QUOTE,)))
        )
    )

    assert bodies(posted) == [message(QUOTE)]


@pytest.mark.unit
@run_async
async def test_same_train_listed_by_other_source_is_not_sent_again() -> None:
    bilkom = BilkomPriceQuote.model_validate(
        QUOTE.model_dump()
        | {
            "source": PriceSourceType.BILKOM,
            "train_label": "IC 1320 (Bilkom)",
            "price_pln": Decimal(41),
        }
    )

    posted = await run(
        Scenario(
            sources=(FakeSource(result=(QUOTE,)), FakeSource(result=(bilkom,)))
        )
    )

    assert bodies(posted) == [message(QUOTE)]


@pytest.mark.unit
@run_async
async def test_failed_source_does_not_stop_other_sources() -> None:
    posted = await run(
        Scenario(
            sources=(
                FakeSource(result=httpx.ConnectError("down")),
                FakeSource(result=(QUOTE,)),
            )
        )
    )

    assert bodies(posted) == [message(QUOTE)]


@pytest.mark.unit
@run_async
async def test_unreadable_topic_sends_nothing() -> None:
    assert await run(Scenario(read_status=500)) == []


@pytest.mark.unit
@run_async
async def test_unreadable_history_sends_nothing() -> None:
    assert await run(Scenario(history_read_status=500)) == []


@pytest.mark.unit
@run_async
async def test_failed_notification_does_not_raise() -> None:
    posted = await run(Scenario(post_status=500))

    assert bodies(posted) == [message(QUOTE)]


@pytest.mark.unit
def test_message_matches_quote_fields() -> None:
    quote = KoleoPriceQuote.model_validate(QUOTE.model_dump())

    assert message(quote) == (
        "warszawa-centralna -> krakow-glowny 23.11 06:04 IC 1320: "
        "45.5 PLN (koleo)\n"
        "https://koleo.pl/rozklad-pkp/warszawa-centralna/krakow-glowny/"
        "23-11-2026_06:04"
    )
