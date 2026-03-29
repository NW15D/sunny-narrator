# Rechunking Guide — Self-Correction via Length Validation

## 📋 Overview

Sunny Narrator implements automatic length-based validation with recursive rechunking to ensure translation quality.

## 🎯 How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Translate chunk (source_len chars)                           │
│    ↓                                                            │
│ 2. Measure translated chunk (target_len chars)                  │
│    ↓                                                            │
│ 3. Calculate difference:                                        │
│    percent_diff = |target_len - source_len| / source_len × 100  │
│    ↓                                                            │
│ 4. Check threshold:                                             │
│    IF percent_diff > threshold AND source_len > MIN_CHUNK_SIZE  │
│    THEN split and retranslate                                   │
│    ↓                                                            │
│ 5. Recursive retry (max depth: 3)                               │
└─────────────────────────────────────────────────────────────────┘
```

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# Length check threshold (percentage)
# Default: 20% - split if length differs by more than 20%
LENGTH_CHECK_THRESHOLD=20

# Minimum chunk size for rechunking
# Chunks smaller than this won't be split (prevents over-splitting)
MIN_CHUNK_SIZE=1000

# Maximum recursion depth
# Prevents infinite loops on problematic text
MAX_DEPTH=3
```

### Recommended Values

| Use Case | LENGTH_CHECK_THRESHOLD | MIN_CHUNK_SIZE | Notes |
|----------|------------------------|----------------|-------|
| **Standard** | 20% | 1000 | Balanced quality/speed |
| **Strict** | 15% | 1000 | Higher quality, more splits |
| **Relaxed** | 25% | 1500 | Faster, fewer splits |
| **Short texts** | 25% | 500 | Allow smaller chunks |

## 📊 Implementation Locations

### 1. app.py (Post-Translation Validation)

**Location:** `app.py:process_chunk_recursive()`

```python
# Check for rechunking need
target_len = len(final_content)
percent_diff = abs(target_len - source_len) / source_len * 100

# Rechunking logic
MIN_CHUNK_SIZE = 1000
should_split = (
    source_len >= MIN_CHUNK_SIZE and
    depth < 3 and
    percent_diff > config.length_check_threshold
)

if should_split:
    # Split and retry
    part1, part2 = ta.split_text_smartly(source_text)
    res1, syn1 = self.process_chunk_recursive(part1, ...)
    res2, syn2 = self.process_chunk_recursive(part2, ...)
    return (res1 or "") + (res2 or ""), ...
```

**When:** After FULL translation of chunk (all 5 stages complete)

**Purpose:** Catch major length discrepancies in final output

### 2. utils.py (Pipeline Stage Validation) — RECOMMENDED

**Location:** `utils.py:TranslationPipeline.execute()`

```python
# After each stage, validate length
def _validate_stage_length(self, source: str, result: str, 
                           stage_name: str) -> bool:
    """Check if stage output length is reasonable."""
    source_len = len(source)
    result_len = len(result)
    percent_diff = abs(result_len - source_len) / source_len * 100
    
    if percent_diff > config.length_check_threshold:
        logger.warning(f"{stage_name}: Length diff {percent_diff:.1f}%")
        return False
    return True
```

**When:** After EACH stage (INITIAL, REFLECTION, IMPROVE, FINAL_EDIT)

**Purpose:** Early detection of issues, before proceeding to next stage

## 🌡️ Temperature Strategy

### Current Implementation

- **Primary LLM (Translation):** `config.temp_translate` (default: 0.01)
- **Secondary LLM (Editing):** `config.temp_proofread` (default: 0.7)

### Recommended Approach

**DON'T lower temperature for all stages** — this reduces quality:

| Stage | Recommended Temp | Reason |
|-------|------------------|--------|
| INITIAL | 0.01-0.1 | Translation needs consistency |
| REFLECTION | 0.3-0.5 | Analysis needs some creativity |
| IMPROVE | 0.3-0.5 | Applying suggestions needs flexibility |
| FINAL_EDIT | 0.1-0.2 | Final polish needs precision |
| SYNOPSIS | 0.1-0.2 | Summary needs accuracy |

### Why Not Lower Temperature for Retries?

**Problem:** Lowering temp on retry assumes the issue was randomness.

**Reality:** Length issues are usually caused by:
1. **Chunk too large** → Split, don't lower temp
2. **Prompt ambiguity** → Improve prompt, don't lower temp
3. **Model limitation** → Different model, not lower temp

**Recommended:** Keep temperature consistent, rely on rechunking instead.

## 📈 Statistics & Monitoring

### Enable Debug Logging

```bash
DEBUG=on
```

### Output Example

```
Chunk 1 (depth 0): 2048 → 2156 chars (5.3%)  ✓ OK
Chunk 2 (depth 0): 2048 → 2689 chars (31.3%)  ⚠ RECHUNK
  Chunk 2a (depth 1): 1024 → 1156 chars (12.9%)  ✓ OK
  Chunk 2b (depth 1): 1024 → 1289 chars (25.9%)  ⚠ RECHUNK
    Chunk 2b-i (depth 2): 512 → 589 chars (15.0%)  ✓ OK
    Chunk 2b-ii (depth 2): 512 → 634 chars (23.8%)  ⚠ RECHUNK
      ... (max depth reached, accept result)
```

### Metrics to Track

```python
rechunk_stats = {
    'total_chunks': 0,
    'rechunked': 0,
    'rechunk_rate': 0.0,  # rechunked / total_chunks
    'avg_depth': 0.0,
    'max_depth_reached': 0,
    'avg_percent_diff': 0.0
}
```

## 🔧 Best Practices

### 1. Tune LENGTH_CHECK_THRESHOLD

**Start with 20%**, then adjust based on rechunk rate:

- **>30% rechunk rate** → Increase threshold to 25%
- **<5% rechunk rate** → Decrease threshold to 15%
- **Target:** 10-20% rechunk rate

### 2. Monitor Language Pairs

Different language pairs have different length ratios:

| Language Pair | Expected Ratio | Recommended Threshold |
|---------------|----------------|----------------------|
| EN → RU | 1.0-1.2 | 20% |
| EN → DE | 1.1-1.3 | 20% |
| EN → ZH | 0.5-0.7 | 30% (Chinese is shorter!) |
| EN → JA | 0.5-0.7 | 30% (Japanese is shorter!) |
| EN → AR | 1.2-1.4 | 25% (Arabic is longer) |

### 3. Set MIN_CHUNK_SIZE Appropriately

- **1000 chars:** Good for most texts
- **500 chars:** For poetry, dialogue-heavy texts
- **1500 chars:** For technical documentation

### 4. Limit Recursion Depth

- **Max depth: 3** (recommended)
- Prevents infinite loops
- If max depth reached frequently, increase threshold

## 🐛 Troubleshooting

### Issue: Too Many Rechunks (>50%)

**Solution:**
1. Increase `LENGTH_CHECK_THRESHOLD` to 25-30%
2. Check if language pair has unusual length ratio
3. Increase `MIN_CHUNK_SIZE` to 1500

### Issue: Translation Quality Poor After Rechunk

**Solution:**
1. Check if context (synopsis) is being passed correctly
2. Verify vocabulary is applied consistently
3. Consider increasing temperature slightly (0.01 → 0.1)

### Issue: Max Depth Reached Frequently

**Solution:**
1. Increase `LENGTH_CHECK_THRESHOLD`
2. Check for problematic source text patterns
3. Consider manual pre-splitting of large sections

## 📝 Changelog

- **2026-03-29:** Documented rechunking strategy
- **2026-03-29:** Added temperature recommendations
- **Previous:** Implemented in app.py (process_chunk_recursive)
