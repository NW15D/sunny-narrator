"""
Test TOC generation in build_output using pandoc.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_toc_pandoc_flag():
    """Test that pandoc TOC flag works correctly."""
    try:
        import pypandoc
    except ImportError:
        print("⚠️  pypandoc not installed - skipping TOC test")
        return
    
    # pandoc 2.9 emits a TOC only for standalone documents (fragment
    # conversion has no TOC element at all); element id is uppercase:
    # <nav id="TOC">. Production does not rely on pandoc --toc anyway
    # (calibre_pipeline._add_toc_to_html builds the TOC itself).
    md = "# Chapter 1\n\n## Section 1.1\n\n### Subsection 1.1.1\n\nText"
    base_args = ['--wrap=none', '--standalone', '--metadata', 'title=Test']
    
    # Test 1: Without TOC flag
    html_no_toc = pypandoc.convert_text(md, 'html', format='markdown', extra_args=base_args)
    has_toc_no_flag = 'id="toc"' in html_no_toc.lower()
    
    # Test 2: With TOC flag
    html_with_toc = pypandoc.convert_text(md, 'html', format='markdown', extra_args=base_args + ['--toc', '--toc-depth=2'])
    has_toc_with_flag = 'id="toc"' in html_with_toc.lower()
    
    print(f"Without --toc flag: TOC present = {has_toc_no_flag}")
    print(f"With --toc flag: TOC present = {has_toc_with_flag}")
    
    if not has_toc_no_flag and has_toc_with_flag:
        print("✅ TOC flag working correctly!")
    elif has_toc_no_flag and has_toc_with_flag:
        print("⚠️  TOC present without flag - pandoc may have default TOC enabled")
    else:
        print("❌ TOC flag not working as expected")
        assert False


def test_build_output_requests_toc_from_calibre():
    """build_output must ask Calibre for a language-independent TOC.

    This test used to assert the opposite — that no TOC was requested —
    because for a long time none was: `ebook-convert` was handed only
    metadata flags, and its default chapter detection matches an English
    keyword list against h1/h2 text, so every translated book shipped with
    empty navigation. The XPath options below replace that keyword matching
    with heading levels, which work in any target language.
    """
    import inspect
    from src.calibre_pipeline import build_output

    source = inspect.getsource(build_output)

    for flag in ("--level1-toc", "--level2-toc", "--chapter", "--max-toc-links"):
        assert flag in source, f"build_output no longer passes {flag} to ebook-convert"
    assert "name()='h1'" in source, (
        "TOC detection must key off heading level, not a language-specific "
        "keyword regex — that is the bug this replaced."
    )


def test_toc_args_reach_ebook_convert(tmp_path):
    """The TOC flags must survive into the actual ebook-convert argv."""
    from unittest.mock import MagicMock, patch
    from src.calibre_pipeline import build_output

    def _fake_run(cmd, *args, **kwargs):
        # ebook-convert writes to cmd[2]; pandoc's cmd[2] is a flag, so its
        # output path has to be read off -o (same stub as the other Calibre
        # tests, inlined because tests/ is not an importable package).
        if cmd[0] == "ebook-convert":
            out = cmd[2]
        else:
            out = cmd[cmd.index('-o') + 1]
        with open(out, 'w', encoding='utf-8') as f:
            f.write('<p>x</p>')
        return MagicMock(returncode=0)

    out = str(tmp_path / 'out.epub')
    with patch('src.calibre_pipeline.check_calibre_installed', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.side_effect = _fake_run
        build_output("# Chapter One\n\nText", "epub",
                     {"title": "T", "author": "A"}, output_path=out)

    ebook_calls = [c.args[0] for c in mock_run.call_args_list
                   if c.args[0][0] == "ebook-convert"]
    assert len(ebook_calls) == 1
    cmd = ebook_calls[0]
    assert cmd[cmd.index("--level1-toc") + 1] == "//*[name()='h1']"
    assert cmd[cmd.index("--level2-toc") + 1] == "//*[name()='h2']"
    assert cmd[cmd.index("--max-toc-links") + 1] == "0"
    assert cmd[cmd.index("--toc-threshold") + 1] == "0"


if __name__ == "__main__":
    print("=" * 60)
    print("Testing TOC Generation Feature")
    print("=" * 60)
    
    test1 = test_toc_pandoc_flag()
    test2 = test_build_output_requests_toc_from_calibre()
    
    results = []
    if test1 is not None:
        results.append(("pypandoc TOC flag", test1))
    if test2 is not None:
        results.append(("build_output TOC", test2))
    
    print(f"\n{'='*60}")
    print("Summary")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL" if result is False else "⚠️  WIP"
        print(f"{status}: {name}")
    
    if all(r for _, r in results):
        print("\n🎉 All TOC tests passed!")
        sys.exit(0)
    else:
        print("\n⚠️  TOC feature needs implementation")
        sys.exit(1)
