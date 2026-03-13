# ── Backend Dockerfile ──────────────────────────────────────────────────────────
# Uses Python 3.11 slim image to keep the container small
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Install system dependencies needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (Python package manager)
RUN pip install --no-cache-dir poetry

# Copy dependency files first (better Docker layer caching)
COPY pyproject.toml poetry.lock* ./

# Install Python dependencies (no virtual env inside Docker - not needed)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy the rest of the backend source code
COPY . .

# Create data directories (uploads, vectordb, etc.)
RUN mkdir -p data/uploads data/vectordb

# Expose the port the API runs on
EXPOSE 8000

# Start the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
