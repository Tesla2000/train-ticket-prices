from datetime import datetime
from typing import ClassVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_validator


class DepartureRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    WARSAW: ClassVar[ZoneInfo] = ZoneInfo("Europe/Warsaw")

    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def _warsaw_when_naive(cls, moment: datetime) -> datetime:
        if moment.tzinfo is None:
            return moment.replace(tzinfo=cls.WARSAW)
        return moment

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end
