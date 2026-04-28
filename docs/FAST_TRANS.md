# FAST_TRANS Mode — Fast Translation

**Version:** 1.16  
**Date:** 2026-03-30

---

> ⚠️ **Compatibility:** JSON mode (`JSON_MODE=true`) works with FAST_TRANS mode.

---

## 📋 Overview

`FAST_TRANS=true` skips quality control stages to accelerate translation.

**Configuration:**
```bash
FAST_TRANS=true    # Fast mode (2 stages)
FAST_TRANS=false   # Standard mode (5 stages)
```

---

## ⚡ Mode Comparison

### Standard (5 stages)

```
Stage 1: INITIAL (Primary LLM)       → Translation
Stage 2: REFLECTION (Secondary LLM)  → Quality review
Stage 3: IMPROVE (Secondary LLM)     → Apply suggestions
Stage 4: FINAL_EDIT (Secondary LLM)  → Proofreading
Stage 5: SYNOPSIS (Secondary LLM)    → Summary
```

**Characteristics:**
- **LLM calls:** 5 (1 Primary + 4 Secondary)
- **Speed:** 1.0x (baseline)
- **Quality:** High

---

### FAST_TRANS (2 stages)

```
Stage 1: INITIAL (Primary LLM)       → Translation
Stage 5: SYNOPSIS (Secondary LLM)    → Summary
(Stages 2-4 skipped)
```

**Characteristics:**
- **LLM calls:** 2 (1 Primary + 1 Secondary)
- **Speed:** ~2.5x faster
- **Quality:** Medium

---

## 📊 Use Cases

### ✅ USE FAST_TRANS=true

| Scenario | Reason |
|----------|---------|
| **Draft translation** | Sufficient for review |
| **Technical documents** | Fewer stylistic requirements |
| **Internal materials** | Not for publication |
| **Quick check** | To assess translation quality |
| **Large volumes** | When speed is more important than quality |

### ❌ DO NOT USE FAST_TRANS=true

| Scenario | Reason |
|----------|---------|
| **Final publication** | Requires high quality |
| **Literary works** | Nuances of style are important |
| **Children's books** | Precision is required |
| **Poetry** | Rhythm and rhyme are critical |
| **Legal documents** | Accuracy of phrasing is essential |

---

## 📈 Performance

### Translation time (1000 chunks):

| Mode | Time | LLM calls |
|-------|-------|-------------|
| **Standard** | ~100 min | 5000 |
| **FAST_TRANS** | ~40 min | 2000 |

**Savings:** ~60% time

---

### Translation Quality:

| Metric | Standard | FAST_TRANS |
|---------|----------|------------|
| **Grammar** | ✅ Excellent | ✅ Good |
| **Style** | ✅ Excellent | ⚠️ Medium |
| **Terminology** | ✅ Consistent | ⚠️ Variations possible |
| **Nuances** | ✅ Preserved | ⚠️ Partially |

---

## 🔧 Configuration

### Basic setting

```bash
FAST_TRANS=true
```

### Combining with other parameters

```bash
# Fast translation + CPU
FAST_TRANS=true
GPU=false

# Fast translation + debug
FAST_TRANS=true
DEBUG=on
```

---

## 📝 Examples

### Example 1: Book draft

```bash
# .env for draft translation
FAST_TRANS=true
DEBUG=off

python app.py
# ~40 min instead of ~100 min
```

### Example 2: Final version

```bash
# .env for final version
FAST_TRANS=false
DEBUG=off

python app.py
# ~100 min, high quality
```

---

## ⚠️ Limitations

### What is lost in FAST_TRANS mode:

1. **REFLECTION (Stage 2)** — No quality analysis
2. **IMPROVE (Stage 3)** — No application of suggestions
3. **FINAL_EDIT (Stage 4)** — No final proofreading

### What is preserved:

1. **INITIAL (Stage 1)** — Base translation
2. **SYNOPSIS (Stage 5)** — Context for subsequent chunks
3. **Vocabulary** — Terminology dictionary
4. **XML structure** — Preservation of tags

---

## 📚 Related documentation

- [TRANSLATION_STAGES.md](TRANSLATION_STAGES.md) — 5-stage pipeline
- [TEMPERATURE_STRATEGY.md](TEMPERATURE_STRATEGY.md) — Temperatures
- [CONFIGURATION.md](CONFIGURATION.md) — All parameters

---

**Version:** 1.16  
**Updated:** 2026-03-30
