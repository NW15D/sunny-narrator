# Use NVIDIA CUDA 12.2 Development image
FROM nvidia/cuda:12.2.0-devel-ubuntu22.04

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install Python and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python3 -m spacy download en_core_web_lg

# Copy application code
COPY . .

# NOTE: The .env file should be provided via --env-file at runtime
# or mapped as a volume if needed.
# The CMD assumes app.py is the entry point
CMD ["python3", "app.py"]