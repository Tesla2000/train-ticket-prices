from enum import StrEnum, auto
from typing import Annotated, Literal

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    RootModel,
    StringConstraints,
    ValidationError,
)

_NTFY_SINCE = Annotated[str, StringConstraints(pattern=r"^(all|\d+[smhd])$")]


class NtfySince(RootModel[_NTFY_SINCE]):
    """Message window for ntfy: "all", or a duration such as "8h" or "30m"."""

    model_config = ConfigDict(frozen=True)


class NtfyEventType(StrEnum):
    MESSAGE = auto()
    OPEN = auto()
    KEEPALIVE = auto()
    POLL_REQUEST = auto()
    MESSAGE_DELETE = auto()
    MESSAGE_CLEAR = auto()


class _NtfyMessageEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    event: Literal[NtfyEventType.MESSAGE]
    message: str


class _NtfyControlEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    event: Literal[
        NtfyEventType.OPEN,
        NtfyEventType.KEEPALIVE,
        NtfyEventType.POLL_REQUEST,
        NtfyEventType.MESSAGE_DELETE,
        NtfyEventType.MESSAGE_CLEAR,
    ]


_NtfyEvent = Annotated[
    _NtfyMessageEvent | _NtfyControlEvent,
    Field(discriminator="event"),
]


class _NtfyEventLine(RootModel[_NtfyEvent]):
    model_config = ConfigDict(frozen=True)


class NtfyTopicReader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    server_url: str = "https://ntfy.sh"
    topic: str
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )

    async def read_messages(
        self, since: NtfySince
    ) -> tuple[str, ...] | Exception:
        try:
            response = await self.client.get(
                f"{self.server_url}/{self.topic}/json",
                params={"poll": "1", "since": since.root},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return error
        try:
            events = tuple(
                _NtfyEventLine.model_validate_json(line).root
                for line in response.text.splitlines()
                if line.strip()
            )
        except ValidationError as error:
            return error
        return tuple(
            event.message
            for event in events
            if isinstance(event, _NtfyMessageEvent)
        )
