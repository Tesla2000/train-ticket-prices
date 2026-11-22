from datetime import datetime
from decimal import Decimal

import httpx
from pydantic import BaseModel, ConfigDict, Field, InstanceOf, SecretStr

from train_ticket_prices.models import DepartureRange, Watch
from train_ticket_prices.ntfy_watch._ntfy_topic_reader import NtfyTopicReader
from train_ticket_prices.stations.types import Station


class NtfyWatchConfigService(BaseModel):
    """Reads the newest config message: one watch per line or per space.

    Watch format: origin->destination;start->end;threshold
    The end is optional and defaults to 23:59 on the start day.
    Spaces are accepted because the ntfy app turns newlines into spaces.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_url: str = "https://ntfy.sh"
    topic: str
    token: SecretStr | None = None
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )

    async def watches(self) -> tuple[Watch, ...] | Exception:
        messages = await NtfyTopicReader(
            server_url=self.server_url,
            topic=self.topic,
            token=self.token,
            client=self.client,
        ).messages("all")
        if isinstance(messages, Exception):
            return messages
        configs = tuple(message for message in messages if ";" in message)
        if not configs:
            return ()
        return self._parse(configs[-1])

    def _parse(self, text: str) -> tuple[Watch, ...] | Exception:
        watches: list[Watch] = []
        for token in text.split():
            watch = self._watch(token)
            if isinstance(watch, Exception):
                return watch
            watches.append(watch)
        return tuple(watches)

    @staticmethod
    def _watch(line: str) -> Watch | Exception:
        try:
            route, when, threshold = line.split(";")
            origin, destination = route.split("->")
            start, _, end = when.partition("->")
            return Watch(
                origin=Station(origin),
                destination=Station(destination),
                departure=DepartureRange(
                    start=datetime.fromisoformat(start),
                    end=datetime.fromisoformat(end or f"{start[:10]}T23:59"),
                ),
                threshold_pln=Decimal(threshold),
            )
        except (ValueError, ArithmeticError) as error:
            return error
