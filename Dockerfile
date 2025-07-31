FROM ghcr.io/astral-sh/uv:bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock .
RUN touch README.md

# Sync the project into a new environment, asserting the lockfile is up to date
RUN uv sync --locked

COPY start_proxy.py .
COPY src src

CMD ["uv", "run", "--no-sync", "start_proxy.py"]
