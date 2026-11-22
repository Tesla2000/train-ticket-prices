import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    SecretStr,
    ValidationError,
)


class _NtfyEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    event: str
    message: str = ""


class NtfyTopicReader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    server_url: str = "https://ntfy.sh"
    topic: str
    token: SecretStr | None = None
    client: InstanceOf[httpx.AsyncClient] = Field(
        exclude=True, default_factory=httpx.AsyncClient
    )

    async def messages(self, since: str) -> tuple[str, ...] | Exception:
        try:
            response = await self.client.get(
                f"{self.server_url}/{self.topic}/json",
                params={"poll": "1", "since": since},
                headers=self.auth_headers(self.token),
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return error
        try:
            events = tuple(
                _NtfyEvent.model_validate_json(line)
                for line in response.text.splitlines()
                if line.strip()
            )
        except ValidationError as error:
            return error
        return tuple(
            event.message for event in events if event.event == "message"
        )

    @staticmethod
    def auth_headers(token: SecretStr | None) -> httpx.Headers:
        """Logged-in requests are rate limited per account, not per shared IP."""
        if token is None:
            return httpx.Headers()
        return httpx.Headers(
            {"Authorization": f"Bearer {token.get_secret_value()}"}
        )
