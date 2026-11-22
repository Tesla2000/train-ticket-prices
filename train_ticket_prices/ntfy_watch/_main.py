from logging import INFO, basicConfig

from pydantic_settings import BaseSettings, SettingsConfigDict

from train_ticket_prices.ntfy_watch._ntfy_watch_service import NtfyWatchService


class NtfyWatchMain(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        cli_parse_args=True,
        cli_kebab_case=True,
    )

    logging_level: int = INFO
    watch: NtfyWatchService

    async def cli_cmd(self) -> None:
        basicConfig(level=self.logging_level)
        await self.watch.run_once()
