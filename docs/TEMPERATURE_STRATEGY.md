# Temperature Strategy — Stage-Specific Control

## 📋 Overview

Sunny Narrator implements **stage-specific temperature control** for optimal translation quality across the 5-stage pipeline.

> ⚠️ **Compatibility:** JSON mode (`JSON_MODE=true`) works with all temperature settings.

## 🌡️ Temperature by Stage

| Stage | LLM | Default Temp | Purpose |
|-------|-----|--------------|---------|
| **1. INITIAL** | Primary | 0.01 | Consistent translation |
| **2. REFLECTION** | Secondary | 0.4 | Creative analysis |
| **3. IMPROVE** | Secondary | 0.4 | Flexible editing |
| **4. FINAL_EDIT** | Secondary | 0.15 | Precise proofreading |
| **5. SYNOPSIS** | Primary | 0.15 | Accurate summary |

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# Base temperatures (fallback)
TEMP_TRANSLATE=0.01      # Primary LLM default
TEMP_PROOFREAD=0.7       # Secondary LLM default

# Stage-specific temperatures (override base)
TEMP_INITIAL=0.01        # Stage 1: Translation consistency
TEMP_REFLECTION=0.4      # Stage 2: Analysis creativity
TEMP_IMPROVE=0.4         # Stage 3: Editing flexibility
TEMP_FINAL_EDIT=0.15     # Stage 4: Proofreading precision
TEMP_SYNOPSIS=0.15       # Stage 5: Summary accuracy
```

### Recommended Values by Model

#### Primary LLM (Translation)

| Model | TEMP_INITIAL | TEMP_SYNOPSIS | Notes |
|-------|--------------|---------------|-------|
| Hunyuan | 0.01 | 0.15 | Very consistent |
| Gemma-2 | 0.05 | 0.15 | Slightly higher for creativity |
| Mistral | 0.01 | 0.15 | Very consistent |
| Llama-3 | 0.01 | 0.15 | Very consistent |
| Qwen | 0.01 | 0.15 | Very consistent |

#### Secondary LLM (Editing)

| Model | TEMP_REFLECTION | TEMP_IMPROVE | TEMP_FINAL_EDIT | Notes |
|-------|-----------------|--------------|-----------------|-------|
| Mistral-7B | 0.4 | 0.4 | 0.15 | Balanced |
| Ministral-8B | 0.4 | 0.4 | 0.15 | Balanced |
| Qwen-2.5-7B | 0.5 | 0.5 | 0.2 | Slightly more creative |
| Gemma-2-9B | 0.5 | 0.5 | 0.2 | More creative |

## 🎯 Why Stage-Specific?

### Problem with Single Temperature

Using one temperature for all stages causes trade-offs:

- **Low temp (0.01):** Good for translation, bad for analysis
- **High temp (0.7):** Good for analysis, bad for translation

### Solution: Stage-Specific

Each stage has different requirements:

| Stage | Requirement | Optimal Temp |
|-------|-------------|--------------|
| INITIAL | Consistency, accuracy | 0.01 (very low) |
| REFLECTION | Creative analysis, nuance detection | 0.4 (medium) |
| IMPROVE | Flexible application of suggestions | 0.4 (medium) |
| FINAL_EDIT | Precision, tag restoration | 0.15 (low) |
| SYNOPSIS | Accurate summarization | 0.15 (low) |

## 📊 Temperature Effects

### Low Temperature (0.01-0.15)

**Pros:**
- ✅ Consistent output
- ✅ Accurate terminology
- ✅ Predictable results
- ✅ Good for technical content

**Cons:**
- ❌ Less creative
- ❌ May miss nuances
- ❌ Rigid phrasing

**Best for:** INITIAL, FINAL_EDIT, SYNOPSIS

### Medium Temperature (0.3-0.5)

**Pros:**
- ✅ Creative analysis
- ✅ Nuance detection
- ✅ Flexible editing
- ✅ Better style suggestions

**Cons:**
- ❌ Less predictable
- ❌ May introduce variations

**Best for:** REFLECTION, IMPROVE

### High Temperature (0.6-0.8)

**Pros:**
- ✅ Very creative
- ✅ Diverse suggestions

**Cons:**
- ❌ Inconsistent
- ❌ May hallucinate
- ❌ Unreliable for translation

**Not recommended** for any stage in translation pipeline.

## 🔧 Implementation

### Code Flow

```python
# LLMService.complete() receives stage parameter
text = llm_service.complete(
    role=LLMRole.PROOFREAD,
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    max_tokens=config.max_len_chunk,
    stage=TranslationStage.REFLECTION  # ← Stage-specific temp
)

# get_temperature_for_stage() selects appropriate temp
def get_temperature_for_stage(self, stage, role):
    if stage == TranslationStage.REFLECTION:
        return config.temp_reflection  # 0.4
    elif stage == TranslationStage.IMPROVE:
        return config.temp_improve  # 0.4
    # ... etc
```

### Logging

With `DEBUG=on`, you'll see temperature in logs:

```
DEBUG: LLM Request [secondary]: Ministral8b, 1234 chars, temp=0.40, sys_not_promt=False
DEBUG: LLM Request [primary]: Hunyuan, 5678 chars, temp=0.01, sys_not_promt=False
DEBUG: LLM Request [secondary]: Ministral8b, 2345 chars, temp=0.15, sys_not_promt=False
```

## 🧪 Tuning Guide

### Signs Temperature is Too Low

- Reflection suggestions are generic/repetitive
- Improve stage doesn't apply suggestions creatively
- Translation is accurate but stiff/unnatural

**Fix:** Increase TEMP_REFLECTION and TEMP_IMPROVE by 0.1

### Signs Temperature is Too High

- Inconsistent terminology in INITIAL
- Synopsis varies wildly between chunks
- FINAL_EDIT introduces new errors

**Fix:** Decrease TEMP_INITIAL and TEMP_SYNOPSIS by 0.05

### Language-Specific Adjustments

| Language Pair | Adjustment | Reason |
|---------------|------------|--------|
| EN→RU | Standard | Well-supported |
| EN→ZH | +0.05 TEMP_INITIAL | Character selection needs flexibility |
| EN→JA | +0.05 TEMP_INITIAL | Honorifics need flexibility |
| EN→AR | +0.05 TEMP_FINAL_EDIT | Script variations |

## 📈 Monitoring

### Track Temperature Effectiveness

```python
# In your monitoring code
temp_stats = {
    'INITIAL': {'temp': 0.01, 'avg_length_diff': 15.2},
    'REFLECTION': {'temp': 0.4, 'avg_suggestions': 4.5},
    'IMPROVE': {'temp': 0.4, 'avg_improvement': 12.3},
    'FINAL_EDIT': {'temp': 0.15, 'avg_length_diff': 5.1},
    'SYNOPSIS': {'temp': 0.15, 'avg_quality': 0.92}
}
```

### A/B Testing

Test different temperatures on same text:

```bash
# Test A: Standard
TEMP_REFLECTION=0.4
TEMP_IMPROVE=0.4

# Test B: More creative
TEMP_REFLECTION=0.5
TEMP_IMPROVE=0.5

# Compare quality of suggestions and improvements
```

## 🐛 Troubleshooting

### Issue: Reflection Suggestions Too Generic

**Symptoms:**
- Same suggestions for every chunk
- No specific terminology feedback

**Solution:**
```bash
TEMP_REFLECTION=0.5  # Increase from 0.4
```

### Issue: Translation Inconsistent

**Symptoms:**
- Same term translated differently
- Unstable output

**Solution:**
```bash
TEMP_INITIAL=0.01  # Decrease to minimum
```

### Issue: Synopsis Inaccurate

**Symptoms:**
- Missing key plot points
- Wrong character genders

**Solution:**
```bash
TEMP_SYNOPSIS=0.1  # Decrease from 0.15
```

## 📝 Changelog

- **2026-03-29:** Implemented stage-specific temperatures
- **2026-03-29:** Added TEMP_INITIAL, TEMP_REFLECTION, TEMP_IMPROVE, TEMP_FINAL_EDIT, TEMP_SYNOPSIS
- **Previous:** Single temperature (TEMP_TRANSLATE, TEMP_PROOFREAD)
