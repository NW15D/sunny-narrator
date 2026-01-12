# Use NVIDIA CUDA 12.2 Development image (includes CUDA headers for compilation)
# Base OS is Ubuntu 22.04
FROM nvidia/cuda:12.2.0-devel-ubuntu22.04

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install Python and build dependencies
# Ubuntu 22.04 usage likely defaults to Python 3.10
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Upgrade pip and install dependencies
# Note: we use python3 -m pip to ensure we use the installed python3
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# NOTE: Environment variables are loaded from the .env file by the application code (using python-dotenv).
# However, for Docker, valid variables should be passed at runtime or mounted.
# Example usage:
# docker run --gpus all --env-file .env -v $(pwd)/books:/app/books my-app

# Command to run the application
CMD ["python3", "app.py"]