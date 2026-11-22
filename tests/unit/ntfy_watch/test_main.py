import runpy
import sys
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_settings import CliApp

from tests.unit.price_source.fixtures import run_async
from train_ticket_prices.ntfy_watch import NtfyWatchMain
from train_ticket_prices.ntfy_watch._ntfy_watch_service import NtfyWatchService


@pytest.mark.unit
def test_entrypoint_hands_main_to_cli_app() -> None:
    with patch.object(CliApp, "run") as cli_run:
        runpy.run_module("train_ticket_prices.ntfy_watch", run_name="__main__")

    cli_run.assert_called_once_with(NtfyWatchMain)


@pytest.mark.unit
def test_topics_are_injected_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ntfy_watch"])
    monkeypatch.setenv("WATCH__CONFIG__TOPIC", "config")
    monkeypatch.setenv("WATCH__HISTORY__TOPIC", "trains")
    monkeypatch.setenv("WATCH__NOTIFIER__TOPIC", "trains")

    main = NtfyWatchMain()

    assert main.watch.config.topic == "config"
    assert main.watch.history.topic == "trains"
    assert main.watch.notifier.topic == "trains"


@pytest.mark.unit
@run_async
async def test_cli_runs_one_check() -> None:
    run_once = AsyncMock()
    watch = NtfyWatchService.model_construct(
        config=None, history=None, notifier=None, sources=(), window="12h"
    )

    with patch.object(NtfyWatchService, "run_once", run_once):
        await NtfyWatchMain.model_construct(watch=watch).cli_cmd()

    run_once.assert_awaited_once()
