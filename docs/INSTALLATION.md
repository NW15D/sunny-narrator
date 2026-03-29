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
git clone https://gt.farhome.ru/sn/sunny-narrator.git
cd sunny-narrator

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (CPU version)
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_lg

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

### Step 2: Install PyTorch with CUDA 12.1

```bash
# Uninstall CPU version
pip uninstall torch torchvision torchaudio -y

# Install GPU version
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Step 3: Install spaCy with CUDA

```bash
# Uninstall CPU version
pip uninstall spacy spacy-transformers -y

# Install GPU version
pip install "spacy[cuda12x]"
python -m spacy download en_core_web_lg
```

### Step 4: Install CuPy (for NER acceleration)

```bash
# Get GPU compute capability
nvidia-smi --query-gpu=compute_cap --format=csv,noheader

# Install cupy with CUDA 12
pip install cupy-cuda12x
```

### Step 5: Verify GPU

```bash
python3 -c "
import torch
import spacy

print('PyTorch CUDA:', torch.cuda.is_available())
print('spaCy GPU:', spacy.prefer_gpu())
"
```

Should output:
```
PyTorch CUDA: True
spaCy GPU: True
```

---

## ⚠️ Troubleshooting

### Issue: NVRTC Error

```
Error loading spaCy model: nvrtc: error: invalid value for --gpu-architecture
```

**Solution 1: Use CPU for NER**

In `.env`:
```bash
SPACY_USE_GPU=false
```

Or in `src/ner.py`, comment out:
```python
# gpu = spacy.prefer_gpu()  # Disabled to avoid NVRTC errors
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

```
CUDA is not available. Falling back to CPU.
```

**Check:**
```bash
# Verify PyTorch CUDA version
python3 -c "import torch; print(torch.version.cuda)"

# Should show: 12.1 (not None)
```

**Fix:**
```bash
# Reinstall PyTorch with CUDA
pip uninstall torch -y
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

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
| `spacy` | NER (Named Entity Recognition) |
| `torch` | Vector similarity (CPU) |
| `beautifulsoup4` | XML/HTML parsing |
| `pydantic` | Data validation |
| `python-dotenv` | Environment config |

### Optional (GPU Acceleration)

| Package | Purpose | Notes |
|---------|---------|-------|
| `cupy-cuda12x` | GPU acceleration for NER | May cause NVRTC errors |
| `spacy-transformers` | Transformer-based NER | Not needed for standard NER |
| `torch (CUDA)` | GPU vectors | Install from pytorch.org |

### CPU vs GPU Performance

| Task | CPU | GPU | Speedup |
|------|-----|-----|---------|
| NER extraction | ~100ms/1k chars | ~50ms/1k chars | 2x |
| Vocabulary matching | ~200ms/chunk | ~50ms/chunk | 4x |
| Translation (LLM) | N/A | N/A | LLM runs on server |

**Recommendation:** CPU is fine for most use cases. GPU only needed for large books (500k+ chars).

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
python3 -c "import torch; print('CUDA:', torch.cuda.is_available())"
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
# Primary LLM
MODEL_TRANSLATE=Hunyuan
API_BASE_TRANSLATE=http://localhost:11434/v1
API_KEY_TRANSLATE=your-key

# NER Configuration
NER=true
NERMODEL=en_core_web_lg

# GPU/CPU Mode
# Set to false if you get NVRTC errors
SPACY_USE_GPU=false

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

- [PyTorch CUDA Installation](https://pytorch.org/get-started/locally/)
- [spaCy GPU Setup](https://spacy.io/usage#gpu)
- [CuPy Installation](https://docs.cupy.dev/en/stable/install.html)
- [NVIDIA CUDA Compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/)

---

## Changelog

- **2026-03-29:** Added GPU troubleshooting section
- **2026-03-29:** Updated requirements.txt with comments
- **Previous:** Initial installation guide
