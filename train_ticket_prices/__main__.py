from pydantic_settings import CliApp

from train_ticket_prices._main import Main

if __name__ == "__main__":  # pragma: no branch
    CliApp.run(Main)
