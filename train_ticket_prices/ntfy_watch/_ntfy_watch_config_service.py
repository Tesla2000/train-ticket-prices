from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from train_ticket_prices.models import DepartureRange, PriceAlert
from train_ticket_prices.ntfy_watch._ntfy_topic_reader import (
    NtfySince,
    NtfyTopicReader,
)
from train_ticket_prices.stations import Station


class NtfyWatchConfigService(BaseModel):
    """Reads the newest config message: one alert per line or per space.

    PriceAlert format: origin->destination;start->end;threshold
    The end is optional and defaults to 23:59 on the start day.
    Spaces are accepted because the ntfy app turns newlines into spaces.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reader: NtfyTopicReader

    async def load_alerts(self) -> tuple[PriceAlert, ...] | Exception:
        messages = await self.reader.read_messages(NtfySince("all"))
        if isinstance(messages, Exception):
            return messages
        configs = tuple(message for message in messages if ";" in message)
        if not configs:
            return ()
        return self._parse(configs[-1])

    def _parse(self, text: str) -> tuple[PriceAlert, ...] | Exception:
        alerts: list[PriceAlert] = []
        for token in text.split():
            if ";" not in token:
                continue
            alert = self._parse_alert(token)
            if isinstance(alert, Exception):
                return alert
            alerts.append(alert)
        return tuple(alerts)

    @staticmethod
    def _parse_alert(line: str) -> PriceAlert | Exception:
        try:
            route, when, threshold = line.split(";")
            origin, destination = route.split("->")
            start, _, end = when.partition("->")
            return PriceAlert(
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
