# GPU Docker Support for Sunny Narrator

This document describes how to run Sunny Narrator with NVIDIA GPU support for faster NER (Named Entity Recognition) processing.

## Requirements

- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit installed on host
- Docker Compose v2.0+

The image has Calibre (`ebook-convert`) and pandoc, so every input format is
translated in it: FB2/TXT (classic pipeline) and EPUB/DOCX/PDF (Calibre pipeline).
`books/` is mounted read-write: the translation and its checkpoint are written
next to the book.

## Quick Start

```bash
# Build and run with GPU support
docker-compose -f docker-compose.yml up --build
```

## Dockerfile

[`Dockerfile`](../Dockerfile), in short:

- base `nvidia/cuda:12.6.3-runtime-ubuntu24.04` — the CUDA 12.6 runtime libraries
  that `cupy-cuda12x` uses, Python 3.12;
- the project in a venv (`/opt/venv`): `torch==2.14.1+cu126`, then `pip install ".[gpu]"`;
- Calibre (`ebook-convert`) from Ubuntu and pandoc 3.12 (`PANDOC_VERSION` build arg),
  headless (`QT_QPA_PLATFORM=offscreen`);
- spaCy models `en_core_web_lg`, `ru_core_news_lg`;
- entrypoint `python3 app.py`.

## docker-compose.yml

[`docker-compose.yml`](../docker-compose.yml): `.env` as the environment,
`./books` mounted read-write (the translation and its checkpoint are written
next to the book), `./logs`, `./src/prompts.json`, one NVIDIA GPU.

## Pre-built images

Every push to `main` (and every `v*` tag) builds both images in GitHub Actions
(`.github/workflows/docker-publish.yml`), runs the test suite inside each of
them and pushes them to GHCR only when it passes:

```bash
docker pull ghcr.io/nw15d/sunny-narrator:main       # GPU
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu   # CPU
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
docker-compose -f docker-compose.yml exec sunny-narrator nvidia-smi
```

### GPU fallback

If no GPU is available, spaCy (NER) automatically falls back to the CPU; there
is no option to require the GPU. To force the CPU on a GPU host, hide the GPU:
`CUDA_VISIBLE_DEVICES=` (empty).
