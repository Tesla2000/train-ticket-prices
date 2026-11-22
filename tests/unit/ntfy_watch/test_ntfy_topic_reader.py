import json

import httpx
import pytest

from tests.unit.price_source.fixtures import run_async
from train_ticket_prices.ntfy_watch._ntfy_topic_reader import NtfyTopicReader


def reader(transport: httpx.MockTransport) -> NtfyTopicReader:
    return NtfyTopicReader(
        topic="trains", client=httpx.AsyncClient(transport=transport)
    )


@pytest.mark.unit
@run_async
async def test_returns_only_message_events_oldest_first() -> None:
    body = "\n".join(
        [
            json.dumps({"event": "open"}),
            json.dumps({"event": "message", "message": "a"}),
            json.dumps({"event": "message", "message": "b"}),
            "",
            json.dumps({"event": "message", "message": "c"}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/trains/json"
        assert request.url.params["since"] == "12h"
        return httpx.Response(200, text=body)

    result = await reader(httpx.MockTransport(handler)).messages("12h")

    assert result == ("a", "b", "c")


@pytest.mark.unit
@run_async
async def test_http_error_is_returned_as_value() -> None:
    result = await reader(
        httpx.MockTransport(lambda _request: httpx.Response(500))
    ).messages("12h")

    assert isinstance(result, httpx.HTTPError)


@pytest.mark.unit
@run_async
async def test_unreadable_line_is_returned_as_value() -> None:
    result = await reader(
        httpx.MockTransport(
            lambda _request: httpx.Response(200, text="not json")
        )
    ).messages("12h")

    assert isinstance(result, ValueError)
