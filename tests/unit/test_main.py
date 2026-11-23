import runpy
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic_settings import CliApp

from tests.unit.notification.test_notification_services import QUOTE
from tests.unit.price_source.fixtures import WARSAW, run_async
from train_ticket_prices import Main, PriceWatcher
from train_ticket_prices.models import DepartureRange, PriceAlert
from train_ticket_prices.price_source import PriceQuote
from train_ticket_prices.stations import Station

ALERT = PriceAlert(
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

    async def fetch_quotes(self, _watch: PriceAlert) -> object:
        self.calls += 1
        return self.result


class StopLoopError(Exception):
    pass


class FakeNotifier:
    def __init__(self, flush_result: object = None) -> None:
        self.flush_result = flush_result
        self.sent: list[PriceQuote] = []
        self.flushes = 0

    async def notify(self, quote: PriceQuote) -> None:
        self.sent.append(quote)

    async def flush(self) -> object:
        self.flushes += 1
        return self.flush_result


def main(
    sources: tuple[FakeSource, ...],
    notifiers: tuple[FakeNotifier, ...],
    interval_seconds: int | None = None,
) -> Main:
    return Main.model_construct(
        sources=sources,
        notifiers=notifiers,
        interval_seconds=interval_seconds,
    )


@pytest.mark.unit
@run_async
async def test_notifies_only_quotes_below_threshold() -> None:
    notifier = FakeNotifier()

    await main((FakeSource((QUOTE, EXPENSIVE)),), (notifier,)).run((ALERT,))

    assert notifier.sent == [QUOTE]


@pytest.mark.unit
@run_async
async def test_failed_source_is_logged_and_others_still_run() -> None:
    notifier = FakeNotifier()

    await main(
        (FakeSource(httpx.ConnectError("down")), FakeSource((QUOTE,))),
        (notifier,),
    ).run((ALERT,))

    assert notifier.sent == [QUOTE]


@pytest.mark.unit
@run_async
async def test_failed_flush_is_logged_and_others_still_flush() -> None:
    failing = FakeNotifier(flush_result=httpx.ConnectError("down"))
    working = FakeNotifier()

    await main((FakeSource((QUOTE,)),), (failing, working)).run((ALERT,))

    assert failing.sent == [QUOTE]
    assert working.sent == [QUOTE]
    assert failing.flushes == working.flushes == 1


@pytest.mark.unit
@run_async
async def test_drops_are_flushed_after_each_check() -> None:
    notifier = FakeNotifier()

    await main((FakeSource((QUOTE,)),), (notifier,)).run((ALERT,))

    assert notifier.flushes == 1


@pytest.mark.unit
@run_async
async def test_one_shot_run_checks_once() -> None:
    source = FakeSource(())

    await main((source,), (FakeNotifier(),)).run((ALERT,))

    assert source.calls == 1


@pytest.mark.unit
@run_async
async def test_loop_notifies_same_quote_only_once_across_checks() -> None:
    class StoppingSource(FakeSource):
        async def fetch_quotes(self, alert: PriceAlert) -> object:
            if self.calls == 2:  # noqa: PLR2004
                raise StopLoopError
            return await super().fetch_quotes(alert)

    notifier = FakeNotifier()
    source = StoppingSource((QUOTE,))

    with pytest.raises(StopLoopError):
        await main((source,), (notifier,), interval_seconds=0).run((ALERT,))

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

    assert isinstance(main, PriceWatcher)
    assert main.interval_seconds == 60  # noqa: PLR2004


@pytest.mark.unit
@run_async
async def test_cli_cmd_runs_one_pass_without_alerts() -> None:
    run = AsyncMock()

    with (
        patch.object(sys, "argv", ["main"]),
        patch.object(PriceWatcher, "run", run),
    ):
        await Main().cli_cmd()

    run.assert_awaited_once_with(())
