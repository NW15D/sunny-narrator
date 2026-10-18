# Docker

Two images, both with Calibre (`ebook-convert`) and pandoc 3.12, so every input
format is translated in them: FB2/TXT (classic pipeline) and EPUB/DOCX/PDF
(Calibre pipeline).

| Image | Dockerfile | Base | GPU | spaCy models inside |
|---|---|---|---|---|
| `ghcr.io/nw15d/sunny-narrator:main` | [`Dockerfile`](../Dockerfile) | `nvidia/cuda:12.6.3-runtime-ubuntu24.04`, Python 3.12, `pip install ".[gpu]"` (CuPy) | yes (falls back to the CPU without one) | `en_core_web_lg`, `ru_core_news_lg` |
| `ghcr.io/nw15d/sunny-narrator:main-cpu` | [`Dockerfile.cpu`](../Dockerfile.cpu) | `python:3.11-slim-bookworm`, `pip install .` | no | `en_core_web_lg`, `ru_core_news_lg`, `de_core_news_lg`, `fr_core_news_lg`, `es_core_news_lg` |

Other spaCy models (another source language, the target language of the
gender check) are downloaded on first use, so the container needs internet
access for them. Neither image installs torch: spaCy runs on thinc (NumPy, or
CuPy on the GPU).

The GPU only speeds up NER and the dictionary matching (see
[DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md#gpu-cuda-and-cpu-nuances-of-dictionary-work));
the translation itself runs on the LLM servers. With cloud models the CPU
image is all you need.

## Run

```bash
docker pull ghcr.io/nw15d/sunny-narrator:main-cpu      # or :main for the GPU image
mkdir -p books logs
cp env.cloud.sample .env                                # or env.sample for your own LLM servers
# edit .env: the keys, FILE=books/mybook.epub, SOURCE_LANG / TARGET_LANG
cp mybook.epub books/

docker run --rm --env-file .env \
  -v "$PWD/books:/app/books" -v "$PWD/logs:/app/logs" \
  ghcr.io/nw15d/sunny-narrator:main-cpu
# GPU image: add --gpus all and use ...sunny-narrator:main
```

The first run builds `books/mybook_<lang>.dic` and stops for review; the second
translates the book. Everything is written next to the book in `books/`: the
translation, the dictionary, the checkpoint (an interrupted run resumes), the
`.dictcheck.txt` report. `logs/` gets the LLM call log (`LLM_LOGGING=true`).

LLM servers on the host (llama.cpp, Ollama) are not `localhost` inside the
container: use the host's address in `API_BASE_*`, or `--network host` on
Linux.

## docker compose

```bash
docker compose -f docker-compose.cpu.yml run --rm sunny-narrator   # CPU image, built locally
docker compose run --rm sunny-narrator                             # GPU image, built locally
```

Both files read `.env`, mount `./books` (read-write) and `./logs`; the GPU one
also mounts `./src/prompts.json` (edit the prompts without rebuilding) and
reserves one NVIDIA GPU. A translation is a command, not a service: use
`run --rm` (or `up` without `-d`), the container stops when the book is done.

## GPU requirements

- an NVIDIA driver for CUDA 12 (525.60 or newer);
- the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  on the host; check with `docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi`.

Without a GPU the GPU image still works, on the CPU. To force the CPU on a GPU
host, hide the GPU: `CUDA_VISIBLE_DEVICES=` (empty).

## How the images are tested

Every push to `main` (and every `v*` tag) builds both images
(`.github/workflows/docker-publish.yml`, GitLab: `.gitlab-ci.yml`), runs the
whole test suite inside each with its Calibre and pandoc
(`scripts/docker-ci-test.sh`), and pushes them to GHCR only when it passes.
