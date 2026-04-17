FROM python:3.13-slim

WORKDIR /app

ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./
COPY README.md ./

# Install dependencies
RUN uv sync --frozen --no-install-project

# Copy project source
COPY src ./src
COPY config ./config

# Set Python path
ENV PYTHONPATH=/app/src

# Default command (can be overridden in docker-compose)
CMD ["uv", "run", "src/zotero_arxiv_daily/main.py"]
