# Plan: Smart Retry with Modifications

**Date:** 2026-04-28  
**Trigger:** User request - empty LLM responses waste tokens  
**Status:** TODO

---

## Problem

Current retry logic simply repeats the same request:
- Same prompts (system + user)
- Same temperature
- Same max_tokens

Result: Same empty response, wasted tokens.

---

## Analysis

**Current code:** `src/utils.py` lines 530-555
- Max 2 retries (retry_count < 2)
- Simply calls `self.complete()` again with same parameters

---

## Solution: Smart Retry Strategy

### Strategy 1: Lower Temperature
- Retry 1: 50% of current temp (more deterministic)
- Retry 2: 25% of current temp (very conservative)

### Strategy 2: System Prompt Enhancement
- Add to system prompt: "If you cannot translate, return the ORIGINAL text unchanged"
- For JSON mode: "If no content, return {\"translation\": \"\"}"

### Strategy 3: Reduce max_tokens
- If response empty, reduce max_tokens by 50% on retry

### Strategy 4: JSON Mode Fallback
- If JSON mode and empty, try without JSON mode as last resort

---

## Tasks

### Task 1: Add retry_params to complete() signature
**File:** `src/utils.py`  
**Action:** Add `retry_count` parameter to pass modified params

### Task 2: Implement temperature reduction
**Action:** Lower temp on each retry (temp * 0.5, temp * 0.25)

### Task 3: Implement prompt enhancement
**Action:** Add fallback instructions to system_prompt on retry

### Task 4: Implement max_tokens reduction  
**Action:** Reduce max_tokens on retry

### Task 5: Add tests
**File:** `tests/test_smart_retry.py`

---

## Acceptance Criteria

1. Each retry uses different parameters
2. Empty response rate decreases
3. Token waste reduced
4. Tests pass
