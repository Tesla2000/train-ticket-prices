from pydantic_settings import CliApp

from train_ticket_prices.ntfy_watch import NtfyWatchMain

if __name__ == "__main__":  # pragma: no branch
    CliApp.run(NtfyWatchMain)
