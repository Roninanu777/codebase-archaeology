FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# third-party deps only (no src/ needed) -> stable, cacheable layer
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# bake models into the image (needs network: offline envs come later)
RUN /app/.venv/bin/python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); \
CrossEncoder('BAAI/bge-reranker-base')"

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts/hf_boot.sh ./scripts/hf_boot.sh
RUN uv sync --frozen --no-dev

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    ARCHAEOLOGY_CLONES_DIR=/data/clones

EXPOSE 7860
CMD ["bash", "scripts/hf_boot.sh"]
