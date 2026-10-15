FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY tests/fixtures/block-replay-synthetic.json ./tests/fixtures/block-replay-synthetic.json
RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "--no-sync", "openparl-extractor"]
CMD ["evaluate-blocks", "tests/fixtures/block-replay-synthetic.json"]
