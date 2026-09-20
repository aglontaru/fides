FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy project specification & files needed for package metadata
COPY pyproject.toml uv.lock README.md ./
COPY src/ /app/src/

# Install dependencies and project
RUN uv sync --frozen --no-dev

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

CMD ["python", "-m", "fides.mcp_server.server"]
