import asyncio
import html
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from train_ticket_prices.models import PriceAlert
from train_ticket_prices.price_source._price_quote import PriceQuote
from train_ticket_prices.price_source.bilkom._bilkom_price_quote import (
    BilkomPriceQuote,
)
from train_ticket_prices.price_source.types import PriceSourceType
from train_ticket_prices.stations import Station

BASE_URL = "https://bilkom.pl"
BROWSER_HEADERS = {
    "Referer": f"{BASE_URL}/podroz",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
WARSAW = ZoneInfo("Europe/Warsaw")
TRIPS_PER_REQUEST = 4
ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2.0
DEPARTURE_QUERY_FORMAT = "%d%m%Y%H%M"
DEPARTURE_FORMAT = "%d-%m-%Y %H:%M CET"
TRIP_PATTERN = re.compile(r'<li class="el"([^>]*)>(.*?)</li>', re.DOTALL)
ATTRIBUTE_PATTERN = re.compile(r'(data-[a-zA-Z-]+)="([^"]*)"')
METADATA_PATTERN = re.compile(r"<[^>]*carrier-metadata[^>]*>")


class _BilkomStation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str


class _BilkomStationSearch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    stations: tuple[_BilkomStation, ...]


class _BilkomAttributes(BaseModel):
    """Raw HTML attributes: keys lowercased, values unescaped."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_attributes(cls, data: dict[str, str]) -> dict[str, str]:
        return {
            key.lower(): html.unescape(value) for key, value in data.items()
        }


class _BilkomTripTag(_BilkomAttributes):
    id: str = Field(default="1", validation_alias="data-id")
    trip_id: str = Field(validation_alias="data-trip-id")


class _BilkomCode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hafas_id: str = Field(alias="hafasId")


class _BilkomCarrier(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    short_name: str = Field(alias="shortName")


class _BilkomTrainTag(_BilkomAttributes):
    partoftrip: str = Field(validation_alias="data-partoftrip")
    partoftripobj: str = Field(validation_alias="data-partoftripobj")
    number: str = Field(validation_alias="data-number")
    carrierid: str = Field(validation_alias="data-carrierid")
    startdate: str = Field(validation_alias="data-startdate")
    arrivaldate: str = Field(validation_alias="data-arrivaldate")
    departure: str = Field(validation_alias="data-departure")
    arrival: str = Field(validation_alias="data-arrival")
    stations: str = Field(default="", validation_alias="data-stations")


class _BilkomWalkTag(_BilkomAttributes):
    """Bus or walking leg: carries no train data."""

    carrierid: Literal["HAFAS_NO_TRAIN"] = Field(
        validation_alias="data-carrierid"
    )


AnyBilkomMetadataTag = _BilkomTrainTag | _BilkomWalkTag


_BILKOM_METADATA_TAG = TypeAdapter(AnyBilkomMetadataTag)


class _BilkomOfferedTrain(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True
    )

    part_of_trip_id: str = Field(alias="partOfTripId")
    part_of_trip: object = Field(alias="partOfTrip")
    train_number: str = Field(alias="trainNumber")
    carrier: _BilkomCarrier
    departure_date: str = Field(alias="departureDate")
    arrival_date: str = Field(alias="arrivalDate")
    departure_station_code: _BilkomCode = Field(alias="departureStationCode")
    arrival_station_code: _BilkomCode = Field(alias="arrivalStationCode")
    station_ids: tuple[str, ...] = Field(alias="stationIds")
    departure: datetime = Field(exclude=True)


class _BilkomTrip(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True
    )

    id: str
    trip_id: str = Field(alias="tripId")
    offered_trains: tuple[_BilkomOfferedTrain, ...] = Field(
        alias="offeredTrains"
    )


class _BilkomJourneyRequest(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True
    )

    journey_prices: tuple[_BilkomTrip, ...] = Field(alias="journeyPrices")


class _BilkomPrice(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="ignore", populate_by_name=True
    )

    id: str
    trip_id: str = Field(alias="tripId")
    total_price: int = Field(alias="totalPrice")
    error_messages: tuple[str, ...] | None = Field(
        default=None, alias="errorMessages"
    )


class _BilkomPriceResponse(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="ignore", populate_by_name=True
    )

    journey_prices: tuple[_BilkomPrice, ...] = Field(alias="journeyPrices")


class BilkomPriceSourceService(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[PriceSourceType.BILKOM] = PriceSourceType.BILKOM
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )

    async def fetch_quotes(
        self, alert: PriceAlert
    ) -> tuple[PriceQuote, ...] | httpx.HTTPError | ValidationError:
        origin = await self._station_hafas_id(alert.origin)
        if not isinstance(origin, str):
            return origin
        destination = await self._station_hafas_id(alert.destination)
        if not isinstance(destination, str):
            return destination
        trips = await self._trips(alert, origin, destination)
        if not isinstance(trips, tuple):
            return trips
        in_range = tuple(
            trip
            for trip in trips
            if alert.departure.contains(trip.offered_trains[0].departure)
        )
        batches = tuple(
            _BilkomJourneyRequest(
                journeyPrices=in_range[index : index + TRIPS_PER_REQUEST]
            )
            for index in range(0, len(in_range), TRIPS_PER_REQUEST)
        )
        responses = tuple(
            await asyncio.gather(*(self._prices(batch) for batch in batches))
        )
        return tuple(
            self._quote(alert, trip, price)
            for batch, response in zip(batches, responses, strict=True)
            if isinstance(response, _BilkomPriceResponse)
            for trip, price in zip(
                batch.journey_prices, response.journey_prices, strict=True
            )
            if not price.error_messages and price.total_price > 0
        )

    async def _station_hafas_id(
        self, station: Station
    ) -> str | httpx.HTTPError | ValidationError:
        name = station.value.replace("-", " ").title()
        try:
            response = await self.client.get(
                f"{BASE_URL}/stacje/szukaj", params={"q": name}
            )
            response.raise_for_status()
            found = _BilkomStationSearch.model_validate(response.json())
        except (httpx.HTTPError, ValidationError) as error:
            return error
        return found.stations[0].id if found.stations else ""

    async def _trips(
        self, alert: PriceAlert, origin: str, destination: str
    ) -> tuple[_BilkomTrip, ...] | httpx.HTTPError:
        try:
            response = await self.client.get(
                f"{BASE_URL}/podroz",
                params={
                    "poczatkowa": origin,
                    "docelowa": destination,
                    "data": alert.departure.start.strftime(
                        DEPARTURE_QUERY_FORMAT
                    ),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return error
        return self._parse_trips(response.text)

    def _parse_trips(self, page: str) -> tuple[_BilkomTrip, ...]:
        trips = []
        for attributes, block in TRIP_PATTERN.findall(page):
            tag = _BilkomTripTag.model_validate(
                dict(ATTRIBUTE_PATTERN.findall(attributes))
            )
            tags = tuple(
                _BILKOM_METADATA_TAG.validate_python(
                    dict(ATTRIBUTE_PATTERN.findall(meta))
                )
                for meta in METADATA_PATTERN.findall(block)
            )
            offered = tuple(
                self._offered_train(tag)
                for tag in tags
                if isinstance(tag, _BilkomTrainTag)
            )
            if offered:
                trips.append(
                    _BilkomTrip(
                        id=tag.id, tripId=tag.trip_id, offeredTrains=offered
                    )
                )
        return tuple(trips)

    async def _prices(
        self, batch: _BilkomJourneyRequest
    ) -> _BilkomPriceResponse | httpx.HTTPError | ValidationError:
        result = await self._post_prices(batch)
        for _ in range(ATTEMPTS - 1):
            if self._succeeded(result):
                break
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            result = await self._post_prices(batch)
        return result

    async def _post_prices(
        self, batch: _BilkomJourneyRequest
    ) -> _BilkomPriceResponse | httpx.HTTPError | ValidationError:
        try:
            response = await self.client.post(
                f"{BASE_URL}/podroz/ceny",
                content=batch.model_dump_json(by_alias=True),
                headers=BROWSER_HEADERS,
            )
            response.raise_for_status()
            return _BilkomPriceResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError) as error:
            return error

    @staticmethod
    def _succeeded(
        result: _BilkomPriceResponse | httpx.HTTPError | ValidationError,
    ) -> bool:
        return isinstance(result, _BilkomPriceResponse) and all(
            not price.error_messages for price in result.journey_prices
        )

    @staticmethod
    def _quote(
        alert: PriceAlert, trip: _BilkomTrip, price: _BilkomPrice
    ) -> BilkomPriceQuote:
        first = trip.offered_trains[0]
        return BilkomPriceQuote(
            origin=alert.origin,
            destination=alert.destination,
            departure=first.departure,
            train_label=first.train_number,
            price_pln=Decimal(price.total_price) / 100,
        )

    @staticmethod
    def _offered_train(tag: _BilkomTrainTag) -> _BilkomOfferedTrain:
        departure_date = tag.startdate
        return _BilkomOfferedTrain(
            partOfTripId=tag.partoftrip,
            partOfTrip=json.loads(tag.partoftripobj),
            trainNumber=tag.number,
            carrier=_BilkomCarrier(shortName=tag.carrierid),
            departureDate=departure_date,
            arrivalDate=tag.arrivaldate,
            departureStationCode=_BilkomCode(hafasId=tag.departure),
            arrivalStationCode=_BilkomCode(hafasId=tag.arrival),
            stationIds=tuple(tag.stations.split(";")),
            departure=datetime.strptime(
                departure_date, DEPARTURE_FORMAT
            ).replace(tzinfo=WARSAW),
        )
