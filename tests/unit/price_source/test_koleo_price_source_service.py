import httpx
import pytest

from tests.unit.price_source.fixtures import (
    ALERT,
    KOLEO_CONNECTIONS,
    KOLEO_STATIONS,
    json_response,
    run_async,
)
from train_ticket_prices.price_source import (
    KoleoPriceSourceService,
    PriceQuote,
)

HTTP_OK = 200
SEARCH_PAGES = 2


def koleo_client(
    search: object = KOLEO_CONNECTIONS,
    stations_status: int = 200,
    stations: object = KOLEO_STATIONS,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stations"):
            if stations_status != HTTP_OK:
                return httpx.Response(stations_status)
            return json_response(stations)
        if request.url.path.endswith("/eol_connections/search"):
            return json_response(search)
        if request.url.path.endswith("/price"):
            return json_response({"price": "45.5", "purchasable": True})
        return httpx.Response(stations_status)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.unit
@run_async
async def test_returns_quotes_within_departure_range() -> None:
    service = KoleoPriceSourceService(client=koleo_client())

    quotes = await service.fetch_quotes(ALERT)

    assert isinstance(quotes, tuple)
    assert [quote.train_label for quote in quotes] == ["IC 1320"]
    assert isinstance(quotes[0], PriceQuote)
    assert str(quotes[0].price_pln) == "45.5"


@pytest.mark.unit
@run_async
async def test_unknown_station_returns_no_quotes() -> None:
    service = KoleoPriceSourceService(
        client=koleo_client(stations=KOLEO_STATIONS[1:])
    )

    assert await service.fetch_quotes(ALERT) == ()


@pytest.mark.unit
@run_async
async def test_http_failure_is_returned_as_value() -> None:
    service = KoleoPriceSourceService(client=koleo_client(stations_status=500))

    result = await service.fetch_quotes(ALERT)

    assert isinstance(result, httpx.HTTPError)


@pytest.mark.unit
@run_async
async def test_search_failure_is_returned_as_value() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stations"):
            return json_response(KOLEO_STATIONS)
        return httpx.Response(400)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await KoleoPriceSourceService(client=client).fetch_quotes(ALERT)

    assert isinstance(result, httpx.HTTPError)


@pytest.mark.unit
@run_async
async def test_search_pages_until_no_new_connections() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stations"):
            return json_response(KOLEO_STATIONS)
        if request.url.path.endswith("/search"):
            calls.append(request.content.decode())
            return json_response(KOLEO_CONNECTIONS[:1])
        return json_response({"price": "10", "purchasable": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    await KoleoPriceSourceService(client=client).fetch_quotes(ALERT)

    assert len(calls) == SEARCH_PAGES
    assert calls[1].startswith(
        '{"start_id":33605,"end_id":80416,"departure_after":"2026-11-23T06:04:00"'
    )


@pytest.mark.unit
@run_async
async def test_failed_price_request_drops_that_connection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stations"):
            return json_response(KOLEO_STATIONS)
        if request.url.path.endswith("/search"):
            return json_response(KOLEO_CONNECTIONS[:1])
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    assert (
        await KoleoPriceSourceService(client=client).fetch_quotes(ALERT) == ()
    )
