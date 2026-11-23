import asyncio
import functools
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from train_ticket_prices.models import DepartureRange, PriceAlert
from train_ticket_prices.stations import Station

WARSAW = ZoneInfo("Europe/Warsaw")

ALERT = PriceAlert(
    origin=Station.WARSZAWA_CENTRALNA,
    destination=Station.KRAKOW_GLOWNY,
    departure=DepartureRange(
        start=datetime(2026, 11, 23, 6, 0, tzinfo=WARSAW),
        end=datetime(2026, 11, 23, 12, 0, tzinfo=WARSAW),
    ),
    threshold_pln=Decimal(50),
)
KOLEO_STATIONS = [
    {"id": 33605, "name_slug": "warszawa-centralna", "name": "x"},
    {"id": 80416, "name_slug": "krakow-glowny", "name": "y"},
]
KOLEO_CONNECTIONS = [
    {
        "uuid": "early",
        "departure": "2026-11-23T06:04:00+01:00",
        "legs": [{"train_full_name": "IC 1320"}],
    },
    {
        "uuid": "late",
        "departure": "2026-11-23T13:00:00+01:00",
        "legs": [{"train_full_name": "IC 1500"}],
    },
]


def json_response(body: object) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(body).encode())


def run_async(test: Callable[[], Awaitable[None]]) -> Callable[[], None]:
    @functools.wraps(test)
    def run() -> None:
        asyncio.run(test())

    return run
