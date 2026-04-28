# Documentation Update Plan — JSON Mode Implementation

**Date:** 2026-04-28  
**Trigger:** Commit ccd5ee0 (escape curly braces in JSON prompts)  
**Status:** ✅ JSON mode fully implemented  
**Implementation:** commits c3706d4, ccd5ee0, de542d7  

---

## 📋 Overview

JSON mode has been implemented across all 4 translation stages (INITIAL, REFLECTION, IMPROVE, FINAL_EDIT). Documentation needs to be updated to reflect:

1. **JSON_MODE** environment variable (replaces legacy DISABLE_JSON_MODE_* flags)
2. **Structured JSON input/output** for all stages
3. **New prompt categories** in `prompts.json` (initial_translation_json, reflection_json, improve_json, editor_json)
4. **Escaped curly braces** in JSON prompts ({{"translation": "..."}} instead of {"translation": "..."})

---

## 🎯 Priority Matrix

| Priority | Criteria |
|----------|----------|
| **HIGH** | Core user-facing docs, README, configuration guides |
| **MEDIUM** | Technical guides, workflow documentation |
| **LOW** | Reference docs, legacy notes |

---

## 📝 Tasks (Atomic — 1 doc per task)

### HIGH Priority

#### Task 1: Update README.md

**File:** `README.md`  
**Priority:** HIGH  
**Reason:** Main entry point for users, must show JSON mode configuration

**Changes:**
- Add `JSON_MODE=true` to Basic .env example
- Update Configuration section with JSON mode info
- Add link to JSON_MODE_ANALYSIS.md in Documentation table
- Update Quick Start to mention JSON mode as recommended

**Status:** TODO

---

#### Task 2: Update docs/CONFIGURATION.md

**File:** `docs/CONFIGURATION.md`  
**Priority:** HIGH  
**Reason:** Primary configuration reference, must document JSON_MODE variable

**Changes:**
- Add `JSON_MODE` to API Settings table (Primary/Secondary LLM sections)
- Deprecate `DISABLE_JSON_MODE_TRANSLATE` and `DISABLE_JSON_MODE_PROOFREAD` with note
- Add JSON mode behavior: "When JSON_MODE=true, JSON is enabled for all stages"
- Update example configurations (Local LLM, API) to include JSON_MODE=true
- Add cross-reference to JSON_MODE_ANALYSIS.md

**New table entry:**
```markdown
| `JSON_MODE` | `false` | Enable structured JSON for all stages (recommended) |
```

**Status:** TODO

---

#### Task 3: Update docs/PROMPTS_GUIDE.md

**File:** `docs/PROMPTS_GUIDE.md`  
**Priority:** HIGH  
**Reason:** Already has JSON mode section but needs updates for implementation details

**Changes:**
- Update JSON Mode section with current implementation details:
  - New prompt categories: initial_translation_json, reflection_json, improve_json, editor_json
  - Escaped curly braces requirement ({{ }} instead of { })
  - JSON input structure for all 4 stages (copy from JSON_MODE_ANALYSIS.md)
  - JSON output structure by stage
- Add note about prompt category lookup (use *_json category, not system_json/user_text_json keys)
- Update example prompts to show escaped braces

**Status:** TODO

---

#### Task 4: Update docs/TRANSLATION_STAGES.md

**File:** `docs/TRANSLATION_STAGES.md`  
**Priority:** HIGH  
**Reason:** Core workflow documentation, must show JSON mode for all stages

**Changes:**
- Add JSON mode variants for all 4 stages (INITIAL, REFLECTION, IMPROVE, FINAL_EDIT)
- For each stage, add:
  - **JSON Input Format** section (copy from JSON_MODE_ANALYSIS.md)
  - **JSON Output Format** section
  - **Prompt Category** note (e.g., "Use initial_translation_json category")
- Update Stage 2 (REFLECTION) output to show JSON format: `{"suggestions": [...]}`
- Update workflow diagram to mention JSON mode option
- Add cross-reference to JSON_MODE_ANALYSIS.md

**Status:** TODO

---

### MEDIUM Priority

#### Task 5: Update README_RU.md

**File:** `README_RU.md`  
**Priority:** MEDIUM  
**Reason:** Russian version of main README

**Changes:**
- Same updates as Task 1 (README.md)
- Translate JSON mode section to Russian
- Update configuration examples

**Status:** TODO

---

#### Task 6: Update README_CN.md

**File:** `README_CN.md`  
**Priority:** MEDIUM  
**Reason:** Chinese version of main README

**Changes:**
- Same updates as Task 1 (README.md)
- Translate JSON mode section to Chinese
- Update configuration examples

**Status:** TODO

---

#### Task 7: Update README_PT.md

**File:** `README_PT.md`  
**Priority:** MEDIUM  
**Reason:** Portuguese version of main README

**Changes:**
- Same updates as Task 1 (README.md)
- Translate JSON mode section to Portuguese
- Update configuration examples

**Status:** TODO

---

#### Task 8: Update docs/INSTALLATION.md

**File:** `docs/INSTALLATION.md`  
**Priority:** MEDIUM  
**Reason:** Installation guide should mention JSON mode as recommended configuration

**Changes:**
- Add note in Environment Configuration section: "Recommended: JSON_MODE=true for better parsing reliability"
- Update .env example to include JSON_MODE=true
- Add troubleshooting note about JSON parsing errors (fallback to XML mode)

**Status:** TODO

---

### LOW Priority

#### Task 9: Update docs/TEMPERATURE_STRATEGY.md

**File:** `docs/TEMPERATURE_STRATEGY.md`  
**Priority:** LOW  
**Reason:** Reference doc, JSON mode doesn't affect temperatures but should be mentioned

**Changes:**
- Add note that JSON mode works with all temperature settings
- No structural changes needed

**Status:** TODO

---

#### Task 10: Update docs/FAST_TRANS.md

**File:** `docs/FAST_TRANS.md`  
**Priority:** LOW  
**Reason:** FAST_TRANS mode documentation, JSON mode compatibility note

**Changes:**
- Add note: "JSON mode works with FAST_TRANS mode"
- No structural changes needed

**Status:** TODO

---

#### Task 11: Update docs/RECHUNKING_GUIDE.md

**File:** `docs/RECHUNKING_GUIDE.md`  
**Priority:** LOW  
**Reason:** Technical reference, JSON mode doesn't affect rechunking

**Changes:**
- Add compatibility note if needed
- No structural changes expected

**Status:** TODO

---

#### Task 12: Update docs/DICTIONARY_FORMAT.md

**File:** `docs/DICTIONARY_FORMAT.md`  
**Priority:** LOW  
**Reason:** Dictionary format reference, JSON mode uses vocabulary in JSON input

**Changes:**
- Add note about vocabulary field in JSON input
- Cross-reference to JSON_MODE_ANALYSIS.md

**Status:** TODO

---

#### Task 13: Update docs/NER_GUIDE.md

**File:** `docs/NER_GUIDE.md`  
**Priority:** LOW  
**Reason:** NER documentation, JSON mode doesn't affect NER directly

**Changes:**
- Add compatibility note if needed
- No structural changes expected

**Status:** TODO

---

#### Task 14: Update docs/DOCKER_CPU_GUIDE.md

**File:** `docs/DOCKER_CPU_GUIDE.md`  
**Priority:** LOW  
**Reason:** Docker guide, .env.example should include JSON_MODE

**Changes:**
- Update .env example in guide to include JSON_MODE=true
- No structural changes needed

**Status:** TODO

---

#### Task 15: Update docs/GPU_DOCKER.md

**File:** `docs/GPU_DOCKER.md`  
**Priority:** LOW  
**Reason:** GPU Docker guide, .env.example should include JSON_MODE

**Changes:**
- Update .env example in guide to include JSON_MODE=true
- No structural changes needed

**Status:** TODO

---

#### Task 16: Update docs/NER_CPU_FALLBACK_ANALYSIS.md

**File:** `docs/NER_CPU_FALLBACK_ANALYSIS.md`  
**Priority:** LOW  
**Reason:** Analysis doc, JSON mode not related

**Changes:**
- No changes needed (JSON mode unrelated to NER)

**Status:** SKIP

---

## 📊 Summary

| Priority | Count | Files |
|----------|-------|-------|
| **HIGH** | 4 | README.md, CONFIGURATION.md, PROMPTS_GUIDE.md, TRANSLATION_STAGES.md |
| **MEDIUM** | 4 | README_RU.md, README_CN.md, README_PT.md, INSTALLATION.md |
| **LOW** | 7 | TEMPERATURE_STRATEGY.md, FAST_TRANS.md, RECHUNKING_GUIDE.md, DICTIONARY_FORMAT.md, NER_GUIDE.md, DOCKER_CPU_GUIDE.md, GPU_DOCKER.md |
| **SKIP** | 1 | NER_CPU_FALLBACK_ANALYSIS.md |
| **TOTAL** | 16 | 15 docs to update |

---

## 🎯 Execution Plan

1. **Start with HIGH priority** (core user docs)
2. **Then MEDIUM** (localized READMEs, installation)
3. **Finally LOW** (reference docs, minor updates)
4. **Verify** all links to JSON_MODE_ANALYSIS.md work
5. **Test** configuration examples in updated docs

---

## 🔗 References

- **Implementation commits:**
  - c3706d4: JSON mode prompt categories + config logic
  - ccd5ee0: Escape curly braces in JSON prompts
  - de542d7: Update JSON_MODE_ANALYSIS.md
  
- **Existing documentation:**
  - [docs/JSON_MODE_ANALYSIS.md](docs/JSON_MODE_ANALYSIS.md) ✅ (already updated)
  - [docs/superpowers/specs/2026-04-28-json-llm-response-design.md](docs/superpowers/specs/2026-04-28-json-llm-response-design.md)
  - [docs/superpowers/plans/2026-04-28-json-llm-response.md](docs/superpowers/plans/2026-04-28-json-llm-response.md)

- **Code changes:**
  - `src/config.py`: JSON_MODE flag, legacy flag handling
  - `src/utils.py`: JSON prompt categories for all 4 stages
  - `src/prompts.json`: *_json prompt categories with escaped braces

---

**Created:** 2026-04-28  
**Author:** Dev Agent  
**Next step:** Execute tasks in priority order
