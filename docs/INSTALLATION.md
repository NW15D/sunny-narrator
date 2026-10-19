# Installation

| Component | Requirement |
|---|---|
| Python | 3.11 or newer (wheels exist for 3.11–3.13) |
| OS | Linux or macOS; Windows through WSL2 |
| RAM | 4 GB is enough with cloud models; spaCy `*_lg` models take ~1 GB |
| Disk | ~300 MB for the project, ~400 MB per `*_lg` spaCy model |
| GPU | not needed: the models run in the cloud or on your LLM servers; an NVIDIA GPU only speeds up spaCy |
| Calibre, pandoc | for EPUB, DOCX and PDF input (system packages) |

Docker images: [DOCKER.md](DOCKER.md).

## Install

The dependencies come from `pyproject.toml` only (no `requirements.txt`).

```bash
git clone https://github.com/NW15D/sunny-narrator && cd sunny-narrator
python3 -m venv .venv && source .venv/bin/activate     # Debian/Ubuntu: apt install python3-venv
pip install -e .
sudo apt install calibre pandoc                         # macOS: brew install --cask calibre && brew install pandoc
```

`pip install -e .` also gives the `sunny-narrator` command (the same as
`python app.py`).

Optional extras:

| Extra | Install | What for |
|---|---|---|
| `cjk` | `pip install -e ".[cjk]"` | Japanese and Chinese source books: the tokenizers of their spaCy models (sudachipy, sudachidict-core, spacy-pkuseg). Korean needs nothing |
| `gpu` | `pip install -e ".[gpu]"` | CuPy for CUDA 12: spaCy runs NER and word vectors on an NVIDIA GPU |
| `dev` | `pip install -e ".[dev]"` | pytest and ruff, for development ([CONTRIBUTING.md](../CONTRIBUTING.md)) |

spaCy models are downloaded on first use: the model of the source language
(`NERMODEL`, picked by `SOURCE_LANG`, e.g. `en_core_web_lg`) and the small
model of the target language for the gender check (e.g. `ru_core_news_sm`).
Offline, download them beforehand: `python -m spacy download en_core_web_lg`.

## Configure

```bash
cp env.cloud.sample .env    # cloud models: put your OpenRouter or ProxyAPI key in
# or
cp env.sample .env          # every option, set up for your own LLM servers
```

Then set `FILE`, `SOURCE_LANG`, `TARGET_LANG` and `COUNTRY` (the country of the readers: Spanish for `México` differs from Spanish for `España`). Every option:
[CONFIGURATION.md](CONFIGURATION.md).

## Check

```bash
sunny-narrator --help                       # the command and its options
ebook-convert --version && pandoc --version # EPUB/DOCX/PDF input only
```

## The two pipelines

The pipeline follows the input format, there is no option to choose it:

| Input | Pipeline | Output (`OUTPUT_FORMAT`, `--output-format`) |
|---|---|---|
| `.fb2`, `.txt` | classic: works on the FB2 structure directly (poems, stanzas, notes survive) | `fb2` (default) or `epub` |
| `.epub`, `.docx`, `.pdf` | Calibre: `ebook-convert` → HTMLZ → Markdown (pandoc) → translation → HTML → `ebook-convert` | `epub` (default), `docx` or `pdf` |

FB2 is never sent through Calibre: its HTMLZ conversion flattens poems and
stanzas into plain paragraphs.

## GPU (optional)

1. An NVIDIA driver for CUDA 12 (`nvidia-smi` shows 525.60 or newer).
2. `pip install -e ".[gpu]"`.
3. Check:
   ```bash
   python3 -c "from src import ner; import spacy; print(ner.gpu_available(), spacy.prefer_gpu())"
   ```
   `True True` — spaCy runs on the GPU. No torch is needed.

CUDA numbers the GPUs fastest first, so with several GPUs spaCy's device 0 is
not necessarily `nvidia-smi`'s GPU 0; `CUDA_DEVICE_ORDER=PCI_BUS_ID` makes the
numberings match, `CUDA_VISIBLE_DEVICES` picks the GPU, and an empty
`CUDA_VISIBLE_DEVICES=` forces the CPU.

## Troubleshooting

| Error | Fix |
|---|---|
| `Calibre (ebook-convert) is not installed` | `sudo apt install calibre` (EPUB/DOCX/PDF only) |
| `pypandoc` / `pandoc` errors | `sudo apt install pandoc`; check with `pandoc --version` |
| `[E050] Can't find model '…'` | offline or `SPACY_AUTO_DOWNLOAD=false`: `python -m spacy download <model>` |
| `nvrtc: error: invalid value for --gpu-architecture` | CuPy does not support this GPU: hide it (`CUDA_VISIBLE_DEVICES=`) or `pip uninstall cupy-cuda12x` — everything works on the CPU |
| A Japanese or Chinese model fails to load | `pip install -e ".[cjk]"` |
| `pip` builds a package from source and fails | use Python 3.11–3.13 |
| Exit code 3, `the … LLM refused the request` | the key, the access or the model name: see the hint in the message |
