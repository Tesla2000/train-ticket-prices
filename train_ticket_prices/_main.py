from logging import INFO, Logger, basicConfig, getLogger

from pydantic import Field, InstanceOf
from pydantic_settings import BaseSettings, CliSuppress, SettingsConfigDict

from train_ticket_prices._price_watcher import PriceWatcher


class Main(PriceWatcher, BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        cli_parse_args=True,
        cli_kebab_case=True,
    )

    logging_level: int = INFO
    logger: CliSuppress[InstanceOf[Logger]] = Field(
        exclude=True, default_factory=lambda: getLogger(__name__)
    )

    async def cli_cmd(self) -> None:
        basicConfig(level=self.logging_level)
        await self.run(())
