# Installation Guide — Sunny Narrator

## 📋 System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Ubuntu 20.04 | Ubuntu 22.04 |
| **Python** | 3.10 | 3.12 |
| **RAM** | 8 GB | 16 GB |
| **GPU** | Optional | NVIDIA with 8GB+ VRAM |
| **Storage** | 10 GB | 50 GB SSD |

---

## 🚀 Quick Start (CPU - Stable)

```bash
# Clone repository
git clone https://github.com/NW15D/sunny-narrator.git
cd sunny-narrator

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (CPU version, uses pyproject.toml)
pip install -e .

# Download spaCy model
python -m spacy download en_core_web_lg

# CJK sources: the model for SOURCE_LANG (picked and downloaded automatically
# on first use, or by hand) and, for Japanese/Chinese, their tokenizers
pip install -e ".[cjk]"        # sudachipy + sudachidict-core (ja), spacy-pkuseg (zh)
python -m spacy download ko_core_news_lg   # Korean needs nothing extra
python -m spacy download ja_core_news_lg
python -m spacy download zh_core_web_lg

# Configure
cp .env.example .env
# Edit .env with your settings

# Run
python app.py
```

---

## 🎮 GPU Installation (Optional)

### Prerequisites

- NVIDIA GPU with 8GB+ VRAM
- NVIDIA Driver 525.60+ (CUDA 12 compatible)
- Ubuntu 20.04/22.04

### Step 1: Check NVIDIA Driver

```bash
nvidia-smi
```

Should show:
- Driver Version: 525.60+ 
- CUDA Version: 12.0+

### Step 2: Install the GPU extra

```bash
pip install -e ".[gpu]"     # cupy-cuda12x: spaCy runs NER and word vectors on the GPU
```

No torch is needed: spaCy's `*_sm`/`*_lg` pipelines run on thinc, with NumPy
on the CPU and CuPy on the GPU.

### Step 3: Verify GPU

```bash
python3 -c "
import spacy
from src import ner
print('CuPy sees a CUDA device:', ner.gpu_available())
print('spaCy GPU:', spacy.prefer_gpu())
"
```

Should output:
```
CuPy sees a CUDA device: True
spaCy GPU: True
```

---

## ⚠️ Troubleshooting

### Issue: NVRTC Error

```
Error loading spaCy model: nvrtc: error: invalid value for --gpu-architecture
```

**Solution 1: Use CPU for NER**

spaCy uses the GPU whenever it sees one (`spacy.prefer_gpu()`). Hide the GPU
from it for the run:
```bash
CUDA_VISIBLE_DEVICES= python3 app.py
```

**Solution 2: Reinstall CuPy with correct architecture**

```bash
# Get compute capability (e.g., 8.6 for RTX 3090)
nvidia-smi --query-gpu=compute_cap --format=csv,noheader

# Install with specific architecture
CUDA_ARCH=86 pip install cupy-cuda12x
```

**Solution 3: Remove CuPy, use CPU**

```bash
pip uninstall cupy cupy-cuda12x -y
```

NER will work on CPU (slightly slower but stable).

### Issue: CUDA Not Available

With `DEBUG=1` the dictionary build prints `spaCy on the CPU`.

**Check:**
```bash
nvidia-smi                                              # the driver sees the GPU
python3 -c "import cupy; print(cupy.cuda.runtime.getDeviceCount())"   # CuPy sees it (1 or more)
```

**Fix:** install the GPU extra (`pip install -e ".[gpu]"`); `CUDA_VISIBLE_DEVICES`
must not be empty. Without a GPU everything works on the CPU.

### Issue: spaCy Model Not Found

```
OSError: [E050] Can't find model 'en_core_web_lg'
```

**Fix:**
```bash
python -m spacy download en_core_web_lg
```

---

## 📦 Requirements Breakdown

### Core (Required)

| Package | Purpose |
|---------|---------|
| `openai` | LLM API client |
| `spacy` | NER (Named Entity Recognition), word vectors |
| `beautifulsoup4` | XML/HTML parsing |
| `pydantic` | Data validation |
| `python-dotenv` | Environment config |

### Optional (GPU Acceleration)

| Package | Purpose | Notes |
|---------|---------|-------|
| `cupy-cuda12x` | GPU acceleration for NER | May cause NVRTC errors |
| `spacy-curated-transformers`, `torch` | `*_trf` models | Not installed by the project, see [DICTIONARY_FORMAT.md](DICTIONARY_FORMAT.md#gpu-cuda-and-cpu-nuances-of-dictionary-work) |

### CPU vs GPU Performance

| Task | CPU | GPU | Speedup |
|------|-----|-----|---------|
| NER extraction | ~100ms/1k chars | ~50ms/1k chars | 2x |
| Vocabulary matching | ~200ms/chunk | ~50ms/chunk | 4x |
| Translation (LLM) | N/A | N/A | LLM runs on server |

**Recommendation:** CPU is fine for most use cases. GPU only needed for large books (500k+ chars).

---

## 🔄 Calibre Pipeline (Auto-detected)

Sunny Narrator now supports an alternative pipeline that accepts **DOCX/EPUB/PDF** input directly, converts via Calibre to Markdown, translates, and outputs back to **DOCX/EPUB/PDF**.

> The pipeline is selected automatically based on the input file extension:
> `.docx`, `.epub`, `.pdf` → Calibre pipeline. `.fb2`, `.txt` → Classic pipeline.

### Prerequisites

| Dependency | Type | Installation |
|------------|------|-------------|
| `pypandoc` | Python package | `pip install pypandoc` |
| `pandoc` | System package | `sudo apt install pandoc` |
| `calibre` | System package | `sudo apt install calibre` |

### Step 1: Install Python Dependencies

```bash
# Already included in pyproject.toml
pip install -e .
```

### Step 2: Install System Dependencies

```bash
# Pandoc (document converter)
sudo apt install pandoc

# Calibre (ebook conversion)
sudo apt install calibre
```

### Step 3: Verify Installation

```bash
# Check Calibre
ebook-convert --version

# Check Pandoc
pandoc --version

# Check pypandoc
python3 -c "import pypandoc; print('pypandoc OK')"
```

### Usage

```bash
# Basic usage (auto-detected by file extension)
python3 app.py

# Specify output format: epub, docx or pdf for DOCX/EPUB/PDF input;
# fb2 or epub for FB2/TXT input
python3 app.py --output-format epub

# Custom chunk size + fast mode
python3 app.py --max-chunk-size 4000 --fast-mode
```

> ⚠️ **FB2 is NOT supported by the Calibre pipeline.** The Calibre pipeline
> accepts DOCX/EPUB/PDF input and produces DOCX/EPUB/PDF output. For FB2 use
> the **classic pipeline** (default for `.fb2` and `.txt` files), which preserves
> poem/stanza/v structure via direct XML manipulation. Calibre's HTMLZ
> intermediate flattens FB2 structure into plain paragraphs — irreversible
> translation quality loss.

### .env Configuration for Calibre Pipeline

```bash
# Input file (DOCX, EPUB or PDF)
FILE=/path/to/book.epub

# Translation settings
SOURCE_LANG=en
TARGET_LANG=ru
COUNTRY=Россия

# Output format (docx, epub, or pdf)
OUTPUT_FORMAT=epub
```

### Pipeline Flow

```
Input (DOCX/EPUB/PDF)
    ↓
Calibre ebook-convert → HTMLZ
    ↓
Extract HTML + metadata from HTMLZ
    ↓
pypandoc: HTML → Markdown
    ↓
Translate Markdown chunks
    ↓
pypandoc: Markdown → HTML (with TOC)
    ↓
Calibre: HTML → Output (FB2/EPUB)
    ↓
Output file
```

### Troubleshooting

**Error: `pypandoc is not installed`**
```bash
pip install pypandoc
# Also need system pandoc:
sudo apt install pandoc
```

**Error: `Calibre (ebook-convert) is not installed`**
```bash
sudo apt install calibre
# Verify:
ebook-convert --version
```

**Error: `Pandoc conversion failed`**
```bash
# Check pandoc is accessible
which pandoc
pandoc --version
```

---

## 🧪 Testing Installation

### Test 1: Basic Import

```bash
python3 -c "import app; print('✓ OK')"
```

### Test 2: spaCy Model

```bash
python3 -c "import spacy; nlp = spacy.load('en_core_web_lg'); print('✓ OK')"
```

### Test 3: CUDA (if GPU installed)

```bash
python3 -c "import cupy; print('CUDA devices:', cupy.cuda.runtime.getDeviceCount())"
```

### Test 4: NER

```bash
python3 -c "
from src import ner
result = ner.make_vocab('Alice went to Wonderland')
print('NER result:', result[:100] if result else 'No terms')
"
```

---

## 📝 Environment Configuration

### .env File

```bash
# Translate LLM
MODEL_TRANSLATE=Hunyuan
API_BASE_TRANSLATE=http://localhost:11434/v1
API_KEY_TRANSLATE=your-key
JSON_MODE=true    # 🚀 Recommended: structured JSON for all stages

# NER Configuration
NER=true
NERMODEL=en_core_web_lg

# Language
SOURCE_LANG=english
TARGET_LANG=russian
COUNTRY=Россия

# Processing
MAX_LEN_CHUNK=8192
LENGTH_CHECK_THRESHOLD=20
FAST_TRANS=false
DEBUG=off
```

---

## 📚 Additional Resources

- [spaCy GPU Setup](https://spacy.io/usage#gpu)
- [CuPy Installation](https://docs.cupy.dev/en/stable/install.html)
- [NVIDIA CUDA Compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/)

---

## Changelog

- **2026-03-29:** Added GPU troubleshooting section
- **2026-03-29:** Updated requirements.txt with comments
- **Previous:** Initial installation guide
