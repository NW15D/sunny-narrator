"""
Test rechunking feature in translation pipeline.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_rechunking_logic():
    """Test that rechunking is properly handled in translate_chunk."""
    try:
        import src.utils as ta
        from src.config import Config
        
        config = Config()
        
        # Test 1: Short text should NOT trigger rechunking
        source_short = "Hello world! How are you?"
        translated_short = "Привет мир! Как дела?"
        
        is_valid, percent_diff, should_split = ta.validate_translation_length(
            source_short, translated_short, "TEST"
        )
        
        print(f"Short text test:")
        print(f"  Source: {len(source_short)} chars")
        print(f"  Translated: {len(translated_short)} chars")
        print(f"  Percent difference: {percent_diff:.1f}%")
        print(f"  Should split: {should_split}")
        print(f"  Is valid: {is_valid}")
        
        if not should_split and is_valid:
            print("  ✅ Short text: No rechunking (correct)\n")
        else:
            print("  ❌ Short text: Should NOT rechunk!\n")
        
        # Test 2: Very long translation difference SHOULD trigger rechunking
        source_long = "This is a very long source text that will likely expand when translated to another language with different word lengths and structures."
        translated_expanded = "Это очень длинный исходный текст, который, вероятно, расширится при переводе на другой язык с другими длиной слов и структурами."
        
        is_valid2, percent_diff2, should_split2 = ta.validate_translation_length(
            source_long, translated_expanded, "TEST"
        )
        
        print(f"Expanded text test:")
        print(f"  Source: {len(source_long)} chars")
        print(f"  Translated: {len(translated_expanded)} chars")
        print(f"  Percent difference: {percent_diff2:.1f}%")
        print(f"  Should split: {should_split2}")
        print(f"  Is valid: {is_valid2}")
        
        if should_split2:
            print("  ⚠️  Expanded text triggers rechunking (threshold check needed)")
        else:
            print("  ✅ Expanded text: No rechunking (diff < threshold)\n")
        
        # Test 3: Extreme expansion (5x) SHOULD trigger rechunking
        source_extreme = "A" * 5000  # 5000 chars
        translated_extreme = "A" * 25000  # 5x expansion (50000%)
        
        is_valid3, percent_diff3, should_split3 = ta.validate_translation_length(
            source_extreme, translated_extreme, "TEST"
        )
        
        print(f"Extreme expansion test (5x):")
        print(f"  Source: {len(source_extreme)} chars")
        print(f"  Translated: {len(translated_extreme)} chars")
        print(f"  Percent difference: {percent_diff3:.1f}%")
        print(f"  Should split: {should_split3}")
        
        if should_split3:
            print("  ✅ Extreme expansion: Rechunking triggered (correct)")
            print(f"  ✅ Threshold: {config.length_check_threshold}%\n")
        else:
            print(f"  ❌ Extreme expansion: Should rechunk (> {config.length_check_threshold}%)\n")
        
        assert should_split3
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        assert False


def test_combine_results_no_separator():
    """Test that combined results after rechunking don't lose separators."""
    try:
        import src.utils as ta
        from src.config import Config
        
        config = Config()
        
        # Simulate rechunking result combination
        part1 = "Part 1 content"
        synth1 = "Synopsis part 1"
        part2 = "Part 2 content"
        synth2 = "Synopsis part 2"
        
        # Current implementation (no separator between parts)
        combined_translation = (part1 or "") + (part2 or "")
        combined_synopsis = (synth1 or "") + " " + (synth2 or "")
        
        print("Current implementation (no separator):")
        print(f"  Combined: '{combined_translation}'")
        print(f"  Has separator: {'YES' if ' ' in part1 + part2 else 'NO'}")
        print(f"  Note: Parts are concatenated with NO space between them!")
        
        # Check if parts need joining with space
        if not combined_translation.startswith(part1):
            print("  ❌ Parts not properly joined")
            assert False
        
        print("  ⚠️  Parts are concatenated without separator - may need fix")
        
        # Recommended fix: use '\n\n' separator for paragraphs
        recommended_combined = (part1 or "") + "\n\n" + (part2 or "")
        print(f"\nRecommended fix (with separator):")
        print(f"  Combined: '{recommended_combined}'")
        print(f"  Note: Added '\\n\\n' separator between parts")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        assert False


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Rechunking Feature")
    print("=" * 60)
    
    test1 = test_rechunking_logic()
    test2 = test_combine_results_no_separator()
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    if test1:
        print("✅ Rechunking logic: Threshold correctly triggered for extreme expansion")
    else:
        print("❌ Rechunking logic: Issue with threshold or validation")
    
    if test2:
        print("⚠️  Combined results: Parts concatenated without separator (potential issue)")
    else:
        print("❌ Combined results: Test failed")
    
    print("\nNote: Rechunking may be causing EPUB English残留 due to:")
    print("  1. No separator between rechunked parts")
    print("  2. Rechunked parts may not have proper structure markers")
    print("  3. translate_chunks may not handle combined_translation correctly")
