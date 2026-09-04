# GPU Docker Support for Sunny Narrator

This document describes how to run Sunny Narrator with NVIDIA GPU support for faster NER (Named Entity Recognition) processing.

## Requirements

- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit installed on host
- Docker Compose v2.0+

## Quick Start

```bash
# Build and run with GPU support
docker-compose -f docker-compose.gpu.yml up --build
```

## Dockerfile.gpu

```dockerfile
# Production-ready Dockerfile for Sunny Narrator with NVIDIA GPU support
# Based on nvidia/cuda:12.1.0-runtime-ubuntu22.04 for smaller image size

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_VISIBLE_DEVICES=0
ENV PYTHONPATH=/app

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3-dev \
    libgomp1 \
    libxml2-dev \
    libxslt1-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Upgrade pip
RUN python3 -m pip install --upgrade pip setuptools wheel

# Copy the dependency manifest first for better layer caching
COPY pyproject.toml .

# Install Python dependencies with CUDA support ([gpu] adds cupy and
# spacy[cuda12x] on top of the base dependencies)
RUN python3 -m pip install --no-cache-dir ".[gpu]"

# Download spaCy models (multi-language support)
RUN python3 -m spacy download en_core_web_lg && \
    python3 -m spacy download ru_core_news_lg

# Copy application code
COPY app.py .
COPY setup.py .
COPY src/ ./src/

# Create directories for volumes
RUN mkdir -p /app/books /app/output

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import torch; print(f'PyTorch CUDA: {torch.cuda.is_available()}')" || exit 1

# Default entrypoint
ENTRYPOINT ["python3", "app.py"]
```

## docker-compose.gpu.yml

```yaml
version: "3.8"

services:
  sunny-narrator:
    build:
      context: .
      dockerfile: Dockerfile.gpu
    image: sunny-narrator:gpu
    container_name: sunny-narrator-gpu
    env_file:
      - .env
    volumes:
      - ./books:/app/books:ro
      - ./output:/app/output
      - ./.env:/app/.env:ro
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    stdin_open: true
    tty: true
```

## Performance Comparison

| Mode | NER Speed | Image Size | Use Case |
|------|-----------|------------|----------|
| CPU | ~1x | ~500MB | Standard translation |
| GPU | ~5-10x | ~8GB | Large books, batch processing |

## Troubleshooting

### NVIDIA Container Toolkit not installed

```bash
# Install on Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Check GPU availability in container

```bash
docker-compose -f docker-compose.gpu.yml exec sunny-narrator nvidia-smi
```

### Disable GPU fallback

If GPU is not available, the application automatically falls back to CPU. To force GPU mode, set in `.env`:

```bash
NER_GPU_ONLY=true
```
