# ---- base: Python + locked dependencies (no project code yet, for better caching) ----
FROM python:3.12-slim AS base
# git is needed by `migrator migrate` (history of the generated target repo)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./

# ---- dev: everything needed to run tests ----
FROM base AS dev
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
CMD ["pytest", "-q"]

# ---- app: small runtime image with the `migrator` command ----
FROM base AS app
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev \
    && useradd --create-home migrator
USER migrator
ENTRYPOINT ["migrator"]
CMD ["--help"]
