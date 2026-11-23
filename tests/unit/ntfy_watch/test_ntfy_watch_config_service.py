import json
from datetime import datetime
from decimal import Decimal

import httpx
import pytest

from tests.unit.price_source.fixtures import WARSAW, run_async
from train_ticket_prices.models import DepartureRange, PriceAlert
from train_ticket_prices.ntfy_watch import (
    NtfyTopicReader,
    NtfyWatchConfigService,
)
from train_ticket_prices.stations import Station


def service(messages: list[str]) -> NtfyWatchConfigService:
    body = "\n".join(
        json.dumps({"event": "message", "message": message})
        for message in messages
    )
    return NtfyWatchConfigService(
        reader=NtfyTopicReader(
            topic="trains",
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, text=body)
                )
            ),
        ),
    )


@pytest.mark.unit
@run_async
async def test_parses_lines_with_explicit_range() -> None:
    result = await service(
        ["wroclaw-glowny->lodz-kaliska;2026-11-23T06:00->2026-11-23T12:00;30"]
    ).load_alerts()

    assert result == (
        PriceAlert(
            origin=Station.WROCLAW_GLOWNY,
            destination=Station.LODZ_KALISKA,
            departure=DepartureRange(
                start=datetime(2026, 11, 23, 6, 0, tzinfo=WARSAW),
                end=datetime(2026, 11, 23, 12, 0, tzinfo=WARSAW),
            ),
            threshold_pln=Decimal(30),
        ),
    )


@pytest.mark.unit
@run_async
async def test_range_end_defaults_to_end_of_start_day() -> None:
    result = await service(
        ["wroclaw-glowny->lodz-kaliska;2026-11-23T06:00;30"]
    ).load_alerts()

    assert isinstance(result, tuple)
    assert result[0].departure.end == datetime(
        2026, 11, 23, 23, 59, tzinfo=WARSAW
    )


@pytest.mark.unit
@run_async
async def test_newest_config_wins_and_drop_messages_are_ignored() -> None:
    result = await service(
        [
            "wroclaw-glowny->lodz-kaliska;2026-11-23T06:00;30",
            "warszawa-centralna -> krakow-glowny 23.11 06:04 IC 1320: 20 PLN (koleo)",
            "\n  \nwroclaw-glowny->lodz-kaliska;2026-11-24T06:00;40\n\n",
            "wroclaw-glowny -> lodz-kaliska 24.11 06:04 X: 20 PLN (koleo)",
        ]
    ).load_alerts()

    assert isinstance(result, tuple)
    assert len(result) == 1
    assert result[0].departure.start.day == 24  # noqa: PLR2004


@pytest.mark.unit
@run_async
async def test_no_config_message_means_no_watches() -> None:
    assert await service(["x"]).load_alerts() == ()


@pytest.mark.unit
@run_async
async def test_invalid_line_is_returned_as_value() -> None:
    result = await service(
        ["wroclaw-glowny;2026-11-23T06:00;30"]
    ).load_alerts()

    assert isinstance(result, ValueError)


@pytest.mark.unit
@run_async
async def test_unknown_station_is_returned_as_value() -> None:
    result = await service(
        ["nowhere->lodz-kaliska;2026-11-23T06:00;30"]
    ).load_alerts()

    assert isinstance(result, ValueError)


@pytest.mark.unit
@run_async
async def test_http_error_is_returned_as_value() -> None:
    failing = NtfyWatchConfigService(
        reader=NtfyTopicReader(
            topic="trains",
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(500)
                )
            ),
        ),
    )

    assert isinstance(await failing.load_alerts(), httpx.HTTPError)


@pytest.mark.unit
@run_async
async def test_watches_separated_by_spaces_are_parsed() -> None:
    first = "wroclaw-glowny->lodz-chojny;2026-11-28T00:00->2026-11-28T23:59;40"
    second = (
        "wroclaw-glowny->lodz-chojny;2026-11-29T00:00->2026-11-29T23:59;40"
    )

    result = await service([f"{first} {second}"]).load_alerts()

    assert isinstance(result, tuple)
    assert [alert.departure.start.day for alert in result] == [28, 29]


@pytest.mark.unit
@run_async
async def test_words_without_semicolon_are_skipped() -> None:
    alert = "wroclaw-glowny->lodz-chojny;2026-11-28T00:00->2026-11-28T23:59;40"

    result = await service([f"{alert} note from app"]).load_alerts()

    assert isinstance(result, tuple)
    assert len(result) == 1
