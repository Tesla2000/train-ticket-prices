import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf, ValidationError

from train_ticket_prices.models import Watch
from train_ticket_prices.price_source._price_quote import PriceQuote
from train_ticket_prices.price_source.types import PriceSourceType
from train_ticket_prices.stations.types import Station

BASE_URL = "https://api.koleo.pl/v2/main"
HEADERS = {
    "X-KOLEO-Version": "2",
    "X-KOLEO-Client": "Nuxt-ef331c2",
    "Accept": "application/json",
}
SEARCH_HEADERS = {**HEADERS, "Accept-EOL-Response-Version": "2"}
WARSAW = ZoneInfo("Europe/Warsaw")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


class _KoleoStation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    name_slug: str


class _KoleoLeg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    train_full_name: str = ""


class _KoleoConnection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    uuid: str
    departure: datetime
    legs: tuple[_KoleoLeg, ...]


class _KoleoPrice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    price: Decimal
    purchasable: bool


class KoleoPriceSourceService(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[PriceSourceType.KOLEO] = PriceSourceType.KOLEO
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )

    async def fetch_quotes(
        self, watch: Watch
    ) -> tuple[PriceQuote, ...] | httpx.HTTPError | ValidationError:
        stations = await self._stations()
        if not isinstance(stations, tuple):
            return stations
        start_id = self._station_id(stations, watch.origin)
        end_id = self._station_id(stations, watch.destination)
        if start_id is None or end_id is None:
            return ()
        connections = await self._connections(watch, start_id, end_id)
        if not isinstance(connections, tuple):
            return connections
        within = tuple(
            connection
            for connection in connections
            if watch.departure.contains(self._local(connection.departure))
        )
        prices = await asyncio.gather(
            *(self._price(connection.uuid) for connection in within)
        )
        return tuple(
            self._quote(watch, connection, price)
            for connection, price in zip(within, prices, strict=True)
            if isinstance(price, _KoleoPrice) and price.purchasable
        )

    async def _stations(
        self,
    ) -> tuple[_KoleoStation, ...] | httpx.HTTPError | ValidationError:
        try:
            response = await self.client.get(
                f"{BASE_URL}/stations", headers=HEADERS
            )
            response.raise_for_status()
            return tuple(
                _KoleoStation.model_validate(item) for item in response.json()
            )
        except (httpx.HTTPError, ValidationError) as error:
            return error

    async def _connections(
        self, watch: Watch, start_id: int, end_id: int
    ) -> tuple[_KoleoConnection, ...] | httpx.HTTPError | ValidationError:
        found: tuple[_KoleoConnection, ...] = ()
        after = watch.departure.start
        while True:
            page = await self._search(start_id, end_id, after)
            if not isinstance(page, tuple):
                return page
            known = {connection.uuid for connection in found}
            fresh = tuple(c for c in page if c.uuid not in known)
            if not fresh:
                break
            found += fresh
            last = max(
                self._local(connection.departure) for connection in fresh
            )
            if last >= watch.departure.end:
                break
            after = last
        return found

    async def _search(
        self, start_id: int, end_id: int, after: datetime
    ) -> tuple[_KoleoConnection, ...] | httpx.HTTPError | ValidationError:
        try:
            response = await self.client.post(
                f"{BASE_URL}/eol_connections/search",
                headers=SEARCH_HEADERS,
                json={
                    "start_id": start_id,
                    "end_id": end_id,
                    "departure_after": after.strftime(TIME_FORMAT),
                    "only_direct": False,
                },
            )
            response.raise_for_status()
            return tuple(
                _KoleoConnection.model_validate(item)
                for item in response.json()
            )
        except (httpx.HTTPError, ValidationError) as error:
            return error

    async def _price(
        self, uuid: str
    ) -> _KoleoPrice | httpx.HTTPError | ValidationError:
        try:
            response = await self.client.get(
                f"{BASE_URL}/eol_connections/{uuid}/price",
                headers=SEARCH_HEADERS,
            )
            response.raise_for_status()
            return _KoleoPrice.model_validate(response.json())
        except (httpx.HTTPError, ValidationError) as error:
            return error

    def _quote(
        self,
        watch: Watch,
        connection: _KoleoConnection,
        price: _KoleoPrice,
    ) -> PriceQuote:
        return PriceQuote(
            source=PriceSourceType.KOLEO,
            origin=watch.origin,
            destination=watch.destination,
            departure=self._local(connection.departure),
            train_label=connection.legs[0].train_full_name,
            price_pln=price.price,
        )

    @staticmethod
    def _station_id(
        stations: tuple[_KoleoStation, ...], station: Station
    ) -> int | None:
        return next(
            (
                found.id
                for found in stations
                if station.value
                in (found.name_slug, f"{found.name_slug}-{found.id}")
            ),
            None,
        )

    @staticmethod
    def _local(moment: datetime) -> datetime:
        return moment.astimezone(WARSAW)
