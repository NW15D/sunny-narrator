# Sunny Narrator Docker Guide

Production-ready Docker setup with NVIDIA GPU support for spaCy NER and optional LLM inference.

## Quick Start

```bash
# 1. Check your GPU environment
./scripts/check-gpu.sh

# 2. Configure environment
cp .env_sample .env
# Edit .env with your API settings

# 3. Build and run
docker-compose -f docker-compose.gpu.yml build
docker-compose -f docker-compose.gpu.yml run --rm sunny-narrator
```

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | NVIDIA 4GB VRAM | NVIDIA 8GB+ VRAM |
| **RAM** | 8GB | 16GB+ |
| **CPU** | 4 cores | 8+ cores |
| **Disk** | 10GB | 50GB+ (for models) |
| **NVIDIA Driver** | 525.60.13+ | Latest |
| **Docker** | 20.10+ | Latest |
| **NVIDIA Container Toolkit** | Required | Latest |

## Installation

### 1. Install NVIDIA Container Toolkit

```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 2. Verify GPU Access

```bash
./scripts/check-gpu.sh
```

Expected output:
```
✓ nvidia-smi found
✓ Docker found
✓ Docker Compose found
✓ NVIDIA Container Toolkit configured
✓ GPU accessible from containers
```

## Configuration

### Environment Variables

Create `.env` file:

```bash
cp .env_sample .env
```

Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `FILE` | Input book path | `books/Cargo.fb2` |
| `SOURCE_LANG` | Source language | `english` |
| `TARGET_LANG` | Target language | `russian` |
| `API_BASE_TRANSLATE` | Translation API URL | `http://localhost:6155/v1` |
| `MODEL_TRANSLATE` | Translation model | `Hunyuan` |
| `API_BASE_PROOFREAD` | Proofreading API URL | `http://localhost:6150/v1` |
| `MODEL_PROOFREAD` | Proofreading model | `Ministral8b` |

### Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `./books` | `/app/books` | Input books (read-only) |
| `./output` | `/app/output` | Translated output |
| `./.env` | `/app/.env` | Configuration (read-only) |

## Usage

### Build Image

```bash
docker-compose -f docker-compose.gpu.yml build
```

### Run Translation

```bash
# Interactive mode
docker-compose -f docker-compose.gpu.yml run --rm sunny-narrator

# With specific book
docker-compose -f docker-compose.gpu.yml run --rm -e FILE=books/MyBook.fb2 sunny-narrator
```

### Test Setup

```bash
./scripts/test-docker.sh
```

### Shell Access

```bash
docker-compose -f docker-compose.gpu.yml run --rm sunny-narrator bash
```

## Architecture

### Single Container (Current)

```
┌─────────────────────────────────────┐
│  sunny-narrator (single container)  │
│  ├─ Python 3.10 + app.py           │
│  ├─ spaCy + NER models (~2GB)      │
│  ├─ CUDA runtime                   │
│  └─ Volumes: /books, /output       │
└─────────────────────────────────────┘
```

### Microservices (Future)

```
┌───────────┐    ┌───────────┐    ┌───────────┐
│  NER API  │◄──►│ Translator│◄──►│  Web UI   │
│ (spaCy)   │    │  (app.py) │    │ (future)  │
│  :50051   │    │  :8080    │    │  :3000    │
└───────────┘    └───────────┘    └───────────┘
```

## Troubleshooting

### GPU Not Available in Container

```bash
# Check host GPU
nvidia-smi

# Test container GPU access
docker run --rm --gpus all nvidia/cuda:12.1.0-base nvidia-smi

# If fails, reinstall NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Out of Memory

```bash
# Reduce batch size in .env
MAX_LEN_CHUNK=4096

# Or use CPU-only mode (slower)
# Edit docker-compose.gpu.yml, remove deploy.resources
```

### spaCy Model Download Fails

```bash
# Manual download
docker-compose -f docker-compose.gpu.yml run --rm sunny-narrator \
    python3 -m spacy download en_core_web_lg
```

## Performance

Expected performance vs bare metal:

| Component | Overhead | Notes |
|-----------|----------|-------|
| NER (spaCy GPU) | ~5% | Minimal overhead |
| Translation API | ~0% | Network bound |
| File I/O | ~10% | Volume mount overhead |
| **Overall** | **~90%** | Production ready |

## Files

| File | Purpose |
|------|---------|
| `Dockerfile.gpu` | Production GPU-enabled image |
| `docker-compose.gpu.yml` | Compose configuration |
| `scripts/check-gpu.sh` | Environment verification |
| `scripts/test-docker.sh` | Integration tests |
| `DOCKER_README.md` | This file |

## References

- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
- [spaCy GPU Usage](https://spacy.io/usage/spacy-101#gpu)
- [Docker Compose GPU](https://docs.docker.com/compose/gpu-support/)
