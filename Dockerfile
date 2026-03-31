# Sunny Narrator - CPU-only Dockerfile (DEFAULT)
# Lightweight image for systems without NVIDIA GPU
# For GPU support, see docs/GPU_DOCKER.md

FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV GPU=false
ENV NER=true

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy models (multi-language support)
RUN python3 -m spacy download en_core_web_lg && \
    python3 -m spacy download ru_core_news_lg

# Copy application code
COPY app.py .
COPY setup.py .
COPY src/ ./src/

# Create directories for volumes
RUN mkdir -p /app/books /app/output /app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -c "import src.utils; print('OK')" || exit 1

# Default entrypoint
ENTRYPOINT ["python3", "app.py"]

# Labels for documentation
LABEL version="1.12"
LABEL description="Sunny Narrator - AI-powered book translation (CPU-only)"
LABEL gpu="false"
