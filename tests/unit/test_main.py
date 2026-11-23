import runpy
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from pydantic_settings import CliApp

from tests.unit.notification.test_notification_services import QUOTE
from tests.unit.price_source.fixtures import WARSAW, run_async
from train_ticket_prices._main import Main
from train_ticket_prices._price_watch import PriceWatch
from train_ticket_prices.models import DepartureRange, Watch
from train_ticket_prices.price_source import PriceQuote
from train_ticket_prices.stations.types import Station

WATCH = Watch(
    origin=Station.WARSZAWA_CENTRALNA,
    destination=Station.KRAKOW_GLOWNY,
    departure=DepartureRange(
        start=datetime(2026, 11, 23, 6, 0, tzinfo=WARSAW),
        end=datetime(2026, 11, 23, 12, 0, tzinfo=WARSAW),
    ),
    threshold_pln=Decimal(50),
)
EXPENSIVE = QUOTE.model_copy(update={"price_pln": Decimal(90)})


class FakeSource:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    async def fetch_quotes(self, _watch: Watch) -> object:
        self.calls += 1
        return self.result


class StopLoopError(Exception):
    pass


class FakeNotifier:
    def __init__(self, result: object = None) -> None:
        self.result = result
        self.sent: list[PriceQuote] = []

    async def notify(self, quote: PriceQuote) -> object:
        self.sent.append(quote)
        return self.result


def main(
    sources: tuple[FakeSource, ...],
    notifiers: tuple[FakeNotifier, ...],
    interval_seconds: int | None = None,
) -> Main:
    return Main.model_construct(
        watches=(WATCH,),
        sources=sources,
        notifiers=notifiers,
        interval_seconds=interval_seconds,
    )


@pytest.mark.unit
@run_async
async def test_notifies_only_quotes_below_threshold() -> None:
    notifier = FakeNotifier()

    await main((FakeSource((QUOTE, EXPENSIVE)),), (notifier,)).cli_cmd()

    assert notifier.sent == [QUOTE]


@pytest.mark.unit
@run_async
async def test_failed_source_is_logged_and_others_still_run() -> None:
    notifier = FakeNotifier()

    await main(
        (FakeSource(httpx.ConnectError("down")), FakeSource((QUOTE,))),
        (notifier,),
    ).cli_cmd()

    assert notifier.sent == [QUOTE]


@pytest.mark.unit
@run_async
async def test_failed_notifier_is_logged_and_others_still_run() -> None:
    failing = FakeNotifier(result=httpx.ConnectError("down"))
    working = FakeNotifier()

    await main((FakeSource((QUOTE,)),), (failing, working)).cli_cmd()

    assert failing.sent == [QUOTE]
    assert working.sent == [QUOTE]


@pytest.mark.unit
@run_async
async def test_one_shot_run_checks_once() -> None:
    source = FakeSource(())

    await main((source,), (FakeNotifier(),)).cli_cmd()

    assert source.calls == 1


@pytest.mark.unit
@run_async
async def test_loop_notifies_same_quote_only_once_across_checks() -> None:
    class StoppingSource(FakeSource):
        async def fetch_quotes(self, watch: Watch) -> object:
            if self.calls == 2:  # noqa: PLR2004
                raise StopLoopError
            return await super().fetch_quotes(watch)

    notifier = FakeNotifier()
    source = StoppingSource((QUOTE,))

    with pytest.raises(StopLoopError):
        await main((source,), (notifier,), interval_seconds=0).cli_cmd()

    assert source.calls == 2  # noqa: PLR2004
    assert notifier.sent == [QUOTE]


@pytest.mark.unit
def test_entrypoint_hands_main_to_cli_app() -> None:
    with patch.object(CliApp, "run") as cli_run:
        runpy.run_module("train_ticket_prices.__main__", run_name="__main__")

    cli_run.assert_called_once_with(Main)


@pytest.mark.unit
def test_main_is_built_from_cli_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["main", "--interval-seconds", "60"])

    main = Main()

    assert isinstance(main, PriceWatch)
    assert main.interval_seconds == 60  # noqa: PLR2004
