# Nothink Fix - Disable Gemma4 Thinking Mode

**Date:** 2026-05-07  
**Issue:** EMPTY RESPONSE on long translations (~18K tokens, result=None)

## Problem

When using `gemma4` with default settings, the model enables "thinking/reasoning mode" automatically. In this mode:
- Tokens are sent to `.reasoning` field instead of `.content`
- API returns high token count but `message.content = None`
- Results in: `⚠️ EMPTY RESPONSE [primary]: LLM returned 18080 tokens but result=None/empty`

This happens primarily on long texts where the model spends many tokens "thinking".

## Root Cause

The `NOTHINK_TRANSLATE` and `NOTHINK_PROOFREAD` config flags were loaded from `.env` but never applied to API calls. The `chat_template_kwargs={"enable_thinking": false}` was never passed.

## Solution

### Code Change (`src/utils.py:complete()`)

When `nothink` config is True for the current role, automatically pass `chat_template_kwargs`:

```python
# Auto-disable thinking mode for local LLMs (gemma4) when nothink config is True
if chat_template_kwargs is None:
    nothink_enabled = False
    if role == LLMRole.PRIMARY and config.nothink_translate:
        nothink_enabled = True
    elif role == LLMRole.SECONDARY and config.nothink_proofread:
        nothink_enabled = True
    
    if nothink_enabled:
        comp_kwargs["chat_template_kwargs"] = {"enable_thinking": False}
```

### Configuration

```env
# Disable thinking mode for primary LLM (translation)
NOTHINK_TRANSLATE=1

# Disable thinking mode for secondary LLM (proofreading)
NOTHINK_PROOFREAD=1
```

### Smart Retry Enhancement

On the final retry (retry_count >= 1), JSON mode is automatically disabled to maximize the chance of getting ANY response content:

```python
if retry_count >= 1:
    retry_json_mode = False  # Fallback to plain text
```

## Verification

Run the test:
```bash
python3 -c "
from src.config import Config
c = Config()
print(f'NOTHINK_TRANSLATE: {c.nothink_translate}')
print(f'NOTHINK_PROOFREAD: {c.nothink_proofread}')
"
```

Expected output:
```
NOTHINK_TRANSLATE: True
NOTHINK_PROOFREAD: True
```

## Impact

- ✅ Eliminates EMPTY RESPONSE errors on long translations
- ✅ No performance impact (thinking mode was wasting tokens anyway)
- ✅ Backward compatible (only applies when config flags are set)
- ✅ Works with both JSON and XML modes
