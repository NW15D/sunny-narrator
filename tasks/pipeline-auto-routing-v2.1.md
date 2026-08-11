# sunny-narrator: Pipeline Auto-Routing & v2.1

**Status:** in_progress  
**Last updated:** 2026-08-11 15:43 MSK

## Goal
Auto-detect pipeline by input format, remove `--pipeline` flag, cleanup, bump to 2.1

## Plan

| Step | Status |
|------|--------|
| Brainstorming: исследование и дизайн | completed |
| Writing Plans: план реализации | completed |
| Execution: Tasks 1-4 (Implement) | in_progress |
| Execution: Spec Review | pending |
| Execution: Verification (tests) | pending |
| Finishing: commit + интеграция | pending |

## Design Decision
- **Вариант A:** Авто-детект + удалить `--pipeline` флаг полностью
- `.docx/.epub/.pdf` → calibre pipeline
- `.fb2/.txt` → classic pipeline (main)
- `--fast-mode` — кросспайплайновый (исправить help)
- `--output-format`, `--max-chunk-size` — только calibre
- Выходной формат calibre = входной формат по умолчанию

## Tasks

### Task 1: Auto-detect pipeline in app.py
- Remove `--pipeline` arg
- Add auto-detection: `CALIBRE_INPUT_FORMATS = {'.docx', '.epub', '.pdf'}`
- Replace `if args.pipeline == 'new':` with auto-detection
- Fix `--fast-mode` help text

### Task 2: Update documentation
- README.md, README_RU.md, INSTALLATION.md

### Task 3: Cleanup artifacts
- Remove `.worktrees/feature/calibre-fixes`
- Remove `test_example.log`, `test_output.log`
- Clean `__pycache__`

### Task 4: Bump version to 2.1
- `pyproject.toml`: version = "2.1", update description

### Task 5: Verify — run full test suite
### Task 6: Commit

## Key Files
- `~/prj/sunny-narrator/app.py` — main entry, auto-routing
- `~/prj/sunny-narrator/src/calibre_pipeline.py` — unchanged (already has guards)
- `~/prj/sunny-narrator/pyproject.toml` — version bump
- `~/prj/sunny-narrator/docs/superpowers/plans/2026-08-11-pipeline-auto-routing.md` — full plan

## Next Action
Dispatch subagent for Tasks 1-4, then spec review, then tests, then commit.
