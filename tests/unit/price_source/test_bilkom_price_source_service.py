from collections.abc import Iterator
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from tests.unit.price_source.fixtures import WATCH, json_response, run_async
from train_ticket_prices.price_source import (
    BilkomPriceSourceService,
    PriceQuote,
    _bilkom_price_source_service,
)
from train_ticket_prices.price_source._bilkom_price_source_service import (
    _BilkomPrice,
)

TRIP_HTML = (
    '<li class="el" data-id="7" data-trip-id="trip-1">'
    '<div class="carrier-metadata" '
    'data-partoftrip="1|821452|0|51|23112026" data-number="1320" '
    'data-carrierId="IC" data-startDate="23-11-2026 06:04 CET" '
    'data-arrivaldate="23-11-2026 09:56 CET" data-departure="5100065" '
    'data-arrival="5100028" data-stations="5100065;5100028" '
    'data-partoftripobj="{&quot;id&quot;:&quot;1&quot;}"></div>'
    "</li>"
)
STATIONS = {"stations": [{"id": "A=1@O=Warszawa Centralna"}]}
HTTP_OK = 200
PRICE_ATTEMPTS = 2


@pytest.fixture(autouse=True)
def no_retry_delay() -> Iterator[None]:
    with patch.object(_bilkom_price_source_service, "RETRY_DELAY_SECONDS", 0):
        yield


def bilkom_client(
    prices: list[dict[str, object]] | None = None,
    page: str = TRIP_HTML,
    price_status: int = 200,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/stacje/szukaj":
            return json_response(STATIONS)
        if request.url.path == "/podroz":
            return httpx.Response(200, text=page)
        if price_status != HTTP_OK:
            return httpx.Response(price_status)
        journey_prices = prices or [
            {"id": "7", "tripId": "trip-1", "totalPrice": 4550}
        ]
        return json_response({"journeyPrices": journey_prices})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.unit
@run_async
async def test_parses_trips_and_converts_grosze_to_pln() -> None:
    service = BilkomPriceSourceService(client=bilkom_client())

    quotes = await service.fetch_quotes(WATCH)

    assert isinstance(quotes, tuple)
    assert len(quotes) == 1
    assert isinstance(quotes[0], PriceQuote)
    assert quotes[0].price_pln == Decimal("45.50")
    assert quotes[0].train_label == "1320"


@pytest.mark.unit
@run_async
async def test_station_search_failure_is_returned_as_value() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await BilkomPriceSourceService(client=client).fetch_quotes(WATCH)

    assert isinstance(result, httpx.HTTPError)


@pytest.mark.unit
@run_async
async def test_unknown_station_name_returns_no_quotes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/stacje/szukaj":
            return json_response({"stations": []})
        return httpx.Response(200, text="")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await BilkomPriceSourceService(client=client).fetch_quotes(WATCH)

    assert result == ()


@pytest.mark.unit
@run_async
async def test_trips_page_failure_is_returned_as_value() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/stacje/szukaj":
            return json_response(STATIONS)
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await BilkomPriceSourceService(client=client).fetch_quotes(WATCH)

    assert isinstance(result, httpx.HTTPError)


@pytest.mark.unit
@run_async
async def test_trip_without_offered_trains_is_skipped() -> None:
    page = '<li class="el" data-trip-id="trip-1"></li>'
    service = BilkomPriceSourceService(client=bilkom_client(page=page))

    assert await service.fetch_quotes(WATCH) == ()


@pytest.mark.unit
@run_async
async def test_price_request_failure_yields_no_quote() -> None:
    service = BilkomPriceSourceService(client=bilkom_client(price_status=500))

    assert await service.fetch_quotes(WATCH) == ()


@pytest.mark.unit
@run_async
async def test_zero_price_with_error_message_is_dropped() -> None:
    prices = [
        {
            "id": "7",
            "tripId": "trip-1",
            "totalPrice": 0,
            "errorMessages": ["Could not access remote service"],
        }
    ]
    service = BilkomPriceSourceService(client=bilkom_client(prices=prices))

    assert await service.fetch_quotes(WATCH) == ()


@pytest.mark.unit
@run_async
async def test_retries_price_request_after_upstream_error() -> None:
    calls = {"price": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/stacje/szukaj":
            return json_response(STATIONS)
        if request.url.path == "/podroz":
            return httpx.Response(200, text=TRIP_HTML)
        calls["price"] += 1
        if calls["price"] == 1:
            return json_response(
                {
                    "journeyPrices": [
                        {
                            "id": "7",
                            "tripId": "trip-1",
                            "totalPrice": 0,
                            "errorMessages": ["upstream"],
                        }
                    ]
                }
            )
        return json_response(
            {
                "journeyPrices": [
                    {"id": "7", "tripId": "trip-1", "totalPrice": 4550}
                ]
            }
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    quotes = await BilkomPriceSourceService(client=client).fetch_quotes(WATCH)

    assert calls["price"] == PRICE_ATTEMPTS
    assert isinstance(quotes, tuple)
    assert quotes[0].price_pln == Decimal("45.50")


@pytest.mark.unit
def test_null_error_messages_means_no_errors() -> None:
    price = _BilkomPrice.model_validate(
        {
            "id": "1",
            "tripId": "trip",
            "totalPrice": 4550,
            "errorMessages": None,
        }
    )

    assert price.error_messages is None
    assert not price.error_messages
