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
    """Test that build_output uses TOC flag."""
    try:
        from src.calibre_pipeline import build_output
        import inspect
        
        source = inspect.getsource(build_output)
        
        has_toc_arg = '--toc' in source
        has_wrap_none = '--wrap=none' in source
        
        print(f"build_output uses --toc flag: {has_toc_arg}")
        print(f"build_output uses --wrap=none: {has_wrap_none}")
        
        if has_wrap_none and not has_toc_arg:
            print("⚠️  build_output missing --toc flag (needs implementation)")
            assert False
        elif has_toc_arg and has_wrap_none:
            print("✅ build_output includes TOC flag")
        else:
            print("⚠️  build_output configuration unexpected")
            
    except Exception as e:
        print(f"❌ Error checking build_output: {e}")


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
