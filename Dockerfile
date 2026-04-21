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
COPY docker-entrypoint.sh /docker-entrypoint.sh

# Make entrypoint executable
RUN chmod +x /docker-entrypoint.sh

# Set Python path
ENV PYTHONPATH=/app/src

# Use entrypoint script for scheduled runs
ENTRYPOINT ["/docker-entrypoint.sh"]
