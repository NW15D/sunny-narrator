# Sunny Narrator - AI-powered book translation (CUDA/GPU)
# Requires NVIDIA GPU + nvidia-container-toolkit on host

FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV GPU=true
ENV NER=true

# Set working directory
WORKDIR /app

# Install system dependencies (build tools for compiling C extensions like cupy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install project (from pyproject.toml) - [gpu] adds the CUDA packages
# (cupy, spacy[cuda12x]); they are an optional extra rather than base
# dependencies so the project stays installable without a CUDA toolchain.
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[gpu]"

# Download spaCy models (multi-language support)
RUN python3 -m spacy download en_core_web_lg && \
    python3 -m spacy download ru_core_news_lg

# Copy application code
COPY app.py .
COPY src/ ./src/

# Create directories for volumes
RUN mkdir -p /app/books /app/output /app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import torch; print('CUDA:', torch.cuda.is_available())" || exit 1

# Default entrypoint
ENTRYPOINT ["python3", "app.py"]

# Labels
LABEL version="2.0"
LABEL description="Sunny Narrator - AI-powered book translation (GPU/CUDA)"
LABEL gpu="true"
