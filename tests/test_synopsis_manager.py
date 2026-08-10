"""Direct unit tests for src/synopsis_manager.py.

Covers: SectionContext accumulation rules, SynopsisManager public API,
synopsis_cache persistence (tmp_path JSON roundtrip), SynopsisGenerator
fallback extraction, edge cases (empty input, missing sections/files).

Note: SynopsisManager(character_registry=None) falls back to the global
registry singleton, so tests inject a no-op DummyRegistry for determinism.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.synopsis_manager import SectionContext, SynopsisManager, SynopsisGenerator


class DummyRegistry:
    """No-op registry stub to isolate tests from the global singleton."""

    def detect_mentions(self, text, section_idx, chunk_idx):
        pass

    def get_character_context_line(self, section_idx, chunk_idx):
        return ""


def make_manager(**kwargs):
    kwargs.setdefault("character_registry", DummyRegistry())
    return SynopsisManager(**kwargs)


# ---------------------------------------------------------------------------
# SectionContext
# ---------------------------------------------------------------------------

def test_section_context_first_chunk_gets_empty_synopsis():
    ctx = SectionContext(section_idx=0)
    assert ctx.get_synopsis_for_next_chunk() == ""


def test_section_context_accumulates_synopses():
    ctx = SectionContext(section_idx=0)
    ctx.add_chunk_synopsis("AAA")
    ctx.add_chunk_synopsis("BBB")
    assert ctx.get_synopsis_for_next_chunk() == "AAA BBB"
    assert ctx.chunk_synopses == ["AAA", "BBB"]


def test_section_context_keeps_only_last_three_chunks():
    ctx = SectionContext(section_idx=0)
    for s in ["S1", "S2", "S3", "S4"]:
        ctx.add_chunk_synopsis(s)
    # Oldest synopsis (S1) must be dropped to avoid token overflow
    assert ctx.accumulated_synopsis == "S2 S3 S4"
    # Full history is preserved
    assert ctx.chunk_synopses == ["S1", "S2", "S3", "S4"]


# ---------------------------------------------------------------------------
# SynopsisManager.get_synopsis
# ---------------------------------------------------------------------------

def test_get_synopsis_empty_for_first_chunk():
    m = make_manager()
    assert m.get_synopsis(0, 0) == ""


def test_get_synopsis_empty_for_new_section_later_chunk():
    m = make_manager()
    # chunk_idx > 0 but no results recorded yet -> nothing accumulated
    assert m.get_synopsis(5, 3) == ""


def test_get_synopsis_returns_accumulated_after_results():
    m = make_manager()
    m.add_chunk_result(0, 0, "text", generated_synopsis="SYN-A")
    assert m.get_synopsis(0, 1) == "SYN-A"
    m.add_chunk_result(0, 1, "text", generated_synopsis="SYN-B")
    assert m.get_synopsis(0, 2) == "SYN-A SYN-B"


def test_sections_are_independent():
    m = make_manager()
    m.add_chunk_result(0, 0, "text", generated_synopsis="SECTION-0")
    m.add_chunk_result(1, 0, "text", generated_synopsis="SECTION-1")
    assert m.get_synopsis(0, 1) == "SECTION-0"
    assert m.get_synopsis(1, 1) == "SECTION-1"


def test_get_synopsis_does_not_create_side_effects():
    m = make_manager()
    m.get_synopsis(0, 0)
    # get_synopsis lazily creates the section, but no chunk data is added
    stats = m.get_section_stats(0)
    assert stats["chunks"] == 0
    assert stats["total_synopsis_chars"] == 0
    assert m.get_synopsis(0, 1) == ""


# ---------------------------------------------------------------------------
# SynopsisManager.add_chunk_result
# ---------------------------------------------------------------------------

def test_add_chunk_result_truncates_long_synopsis():
    m = make_manager(max_synopsis_chars=10)
    m.add_chunk_result(0, 0, "text", generated_synopsis="X" * 100)
    stored = m.section_contexts[0].chunk_synopses[0]
    assert stored == "X" * 10 + "..."


def test_add_chunk_result_generates_synopsis_from_translation():
    m = make_manager()
    m.add_chunk_result(0, 0, "<p>Hello world. Second sentence.</p>")
    stored = m.section_contexts[0].chunk_synopses[0]
    # First sentence, XML tags stripped
    assert stored == "Hello world"


def test_add_chunk_result_empty_translation():
    m = make_manager()
    m.add_chunk_result(0, 0, "")
    assert m.section_contexts[0].chunk_synopses == [""]


def test_add_chunk_result_calls_registry_detect_mentions():
    calls = []

    class StubRegistry:
        def detect_mentions(self, text, section_idx, chunk_idx):
            calls.append((text, section_idx, chunk_idx))

        def get_character_context_line(self, section_idx, chunk_idx):
            return ""

    m = SynopsisManager(character_registry=StubRegistry())
    m.add_chunk_result(2, 3, "Some text.", generated_synopsis="SYN")
    assert calls == [("Some text.", 2, 3)]


def test_generated_synopsis_includes_character_context():
    class StubRegistry:
        def detect_mentions(self, text, section_idx, chunk_idx):
            pass

        def get_character_context_line(self, section_idx, chunk_idx):
            return "Alice (she)"

    m = SynopsisManager(character_registry=StubRegistry())
    m.add_chunk_result(0, 0, "Alice walked home. It was late.")
    stored = m.section_contexts[0].chunk_synopses[0]
    assert stored == "Alice (she). Alice walked home"


def test_generate_synopsis_respects_max_chars():
    m = make_manager(max_synopsis_chars=20)
    result = m._generate_synopsis("A" * 500 + ".")
    assert len(result) == 20


# ---------------------------------------------------------------------------
# get_section_stats / reset_section
# ---------------------------------------------------------------------------

def test_get_section_stats_missing_section():
    m = make_manager()
    assert m.get_section_stats(99) == {"chunks": 0, "total_synopsis_chars": 0}


def test_get_section_stats_with_data():
    m = make_manager()
    m.add_chunk_result(0, 0, "t", generated_synopsis="AAAA")
    m.add_chunk_result(0, 1, "t", generated_synopsis="BB")
    stats = m.get_section_stats(0)
    assert stats["chunks"] == 2
    assert stats["total_synopsis_chars"] == 6
    assert stats["accumulated_synopsis_chars"] == len("AAAA BB")


def test_reset_section_removes_context():
    m = make_manager()
    m.add_chunk_result(0, 0, "t", generated_synopsis="SYN")
    m.reset_section(0)
    assert 0 not in m.section_contexts
    assert m.get_synopsis(0, 1) == ""


def test_reset_section_missing_is_noop():
    m = make_manager()
    m.reset_section(42)  # must not raise


# ---------------------------------------------------------------------------
# synopsis_cache persistence
# ---------------------------------------------------------------------------

def test_synopsis_cache_getter_format():
    m = make_manager()
    m.add_chunk_result(0, 0, "t", generated_synopsis="A")
    m.add_chunk_result(1, 0, "t", generated_synopsis="B")
    cache = m.synopsis_cache
    assert cache == {"section_0": ["A"], "section_1": ["B"]}


def test_synopsis_cache_setter_rebuilds_accumulated():
    m = make_manager()
    m.synopsis_cache = {"section_3": ["X", "Y"]}
    assert m.get_synopsis(3, 1) == "X Y"
    assert m.get_synopsis(3, 0) == ""


def test_synopsis_cache_setter_ignores_foreign_keys():
    m = make_manager()
    m.synopsis_cache = {"section_0": ["A"], "garbage": ["Z"]}
    assert list(m.section_contexts.keys()) == [0]


def test_synopsis_cache_json_roundtrip_via_file(tmp_path):
    """Persistence: cache -> JSON file -> fresh manager."""
    m = make_manager()
    m.add_chunk_result(0, 0, "t", generated_synopsis="ONE")
    m.add_chunk_result(0, 1, "t", generated_synopsis="TWO")

    path = tmp_path / "synopsis.json"
    path.write_text(json.dumps(m.synopsis_cache), encoding="utf-8")

    m2 = make_manager()
    m2.synopsis_cache = json.loads(path.read_text(encoding="utf-8"))
    assert m2.synopsis_cache == {"section_0": ["ONE", "TWO"]}
    assert m2.get_synopsis(0, 2) == "ONE TWO"


def test_synopsis_cache_restore_from_missing_file(tmp_path):
    """Edge case: no persisted cache -> manager starts empty."""
    m = make_manager()
    path = tmp_path / "does_not_exist.json"
    if path.exists():
        m.synopsis_cache = json.loads(path.read_text())
    assert m.synopsis_cache == {}
    assert m.get_synopsis(0, 1) == ""


# ---------------------------------------------------------------------------
# SynopsisGenerator fallback
# ---------------------------------------------------------------------------

def test_generator_without_llm_uses_fallback():
    gen = SynopsisGenerator()
    assert gen.llm_service is None
    result = gen.generate("First sentence here. Second one.")
    assert result == "First sentence here"


def test_generator_fallback_strips_xml_tags():
    gen = SynopsisGenerator()
    assert gen._fallback_extract("<p>Hello there. Rest.</p>") == "Hello there"


def test_generator_fallback_truncates_long_sentence():
    gen = SynopsisGenerator()
    long_text = "A" * 200
    result = gen._fallback_extract(long_text)
    assert result == "A" * 150 + "..."


def test_generator_fallback_empty_text():
    gen = SynopsisGenerator()
    assert gen._fallback_extract("") == ""


def test_generator_falls_back_when_llm_fails(monkeypatch):
    import src.utils as u

    def broken(**kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(u.llm_service_compat, "complete", broken)
    gen = SynopsisGenerator()
    gen.llm_service = object()  # truthy -> tries LLM path
    result = gen.generate("Fallback wins. Really.")
    assert result == "Fallback wins"
