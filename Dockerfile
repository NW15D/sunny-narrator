# Sunny Narrator - AI-powered book translation (CUDA/GPU)
# Requires NVIDIA GPU + nvidia-container-toolkit on host

# CUDA 12.6 runtime libraries come from the base image (cupy uses them
# directly). Ubuntu 24.04: Python 3.12.
FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV NER=true
# Ubuntu's Python is externally managed (PEP 668): the project lives in a venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Set working directory
WORKDIR /app

# Install system dependencies (Python, build tools for C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-dev \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && python3 -m venv /opt/venv

# Calibre (ebook-convert) and pandoc for the EPUB/DOCX/PDF pipeline.
# pandoc is pinned to the release the project is tested with (the distro one
# is older). ebook-convert runs headless; Qt WebEngine (PDF output) needs
# --no-sandbox as root.
ARG PANDOC_VERSION=3.12
ENV QT_QPA_PLATFORM=offscreen
ENV QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox
RUN apt-get update && apt-get install -y --no-install-recommends calibre \
    && arch="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/pandoc.deb \
       "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-${arch}.deb" \
    && dpkg -i /tmp/pandoc.deb && rm /tmp/pandoc.deb \
    && rm -rf /var/lib/apt/lists/* && apt-get clean \
    && ebook-convert --version && pandoc --version

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# The project from pyproject.toml; [gpu] adds cupy-cuda12x (no torch: spaCy
# runs on thinc with CuPy).
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
    CMD python3 -c "import cupy; print('CUDA devices:', cupy.cuda.runtime.getDeviceCount())" || exit 1

# Default entrypoint
ENTRYPOINT ["python3", "app.py"]

# Labels
LABEL version="2.9.1"
LABEL description="Sunny Narrator - AI-powered book translation (GPU/CUDA)"
LABEL gpu="true"
