FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY train_ticket_prices ./train_ticket_prices
RUN uv sync --frozen --no-dev

CMD ["/app/.venv/bin/python", "-m", "train_ticket_prices.ntfy_watch"]
