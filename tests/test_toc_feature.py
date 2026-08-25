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


def test_build_output_toc_integration():
    """build_output does not currently generate a TOC.

    This used to introspect only inspect.getsource(build_output) for
    '--toc'/'--wrap=none' and assert False when the (permanently absent)
    --toc flag was missing — but the whole body was wrapped in
    `except Exception`, which silently swallowed that AssertionError on
    every run for years (see CLAUDE.md's Calibre pipeline notes). The
    pandoc invocation also moved out of build_output and into
    _markdown_to_html_file (batched Markdown->HTML conversion; see that
    function's docstring), so a source check scoped to build_output alone
    would no longer even see '--wrap=none'.

    This documents the real, current behavior instead: no TOC is
    requested. _add_toc_to_html exists but is dead code — never called
    from build_output or run_pipeline. If TOC generation is implemented
    later, this test should fail loudly and get updated, not silently pass.
    """
    import inspect
    from src.calibre_pipeline import build_output, _markdown_to_html_file

    source = inspect.getsource(build_output) + inspect.getsource(_markdown_to_html_file)

    assert '--wrap=none' in source
    assert '--toc' not in source, (
        "build_output/_markdown_to_html_file now request a TOC from pandoc; "
        "update this test's expectations if that was intentional."
    )


if __name__ == "__main__":
    print("=" * 60)
    print("Testing TOC Generation Feature")
    print("=" * 60)
    
    test1 = test_toc_pandoc_flag()
    test2 = test_build_output_toc_integration()
    
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
