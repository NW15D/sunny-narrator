"""Tests for markdown_utils module."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils import validate_translation_length


def _calibrate_one_to_one():
    from src.utils import length_calibration
    for _ in range(length_calibration.WARMUP):
        length_calibration.record(2000, 2000)


def test_validate_translation_length_rejects_too_long():
    """Test length validation function from src.utils."""
    from src.utils import validate_translation_length
    _calibrate_one_to_one()
    
    # Test chunk with 50% diff (above threshold of 20%) - need >2000 chars for MIN_CHUNK_SIZE
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 2000, "x" * 3000, "test"
    )
    # percent_diff = 50% > threshold 20%, so should_split = True
    assert percent_diff == 50.0
    assert should_split == True
    
    # Test chunk with 51% diff
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 2000, "x" * 3020, "test"
    )
    assert percent_diff == 51.0
    assert should_split == True


def test_validate_translation_length_accepts_ok_and_rejects_small_chunk():
    """Test length validation function from src.utils."""
    _calibrate_one_to_one()
    # Test chunk with 50% diff (source_len >= 2000 required for split)
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 2500, "x" * 3750, "test"  # 50% diff, source >= MIN_CHUNK_SIZE
    )
    # percent_diff = 50% > threshold 20%, so should_split = True
    assert percent_diff == 50.0
    assert should_split == True
    assert is_valid == False

    # Test chunk with 15% diff (below threshold)
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 2500, "x" * 2875, "test"  # 15% diff
    )
    # percent_diff = 15% < threshold 20%, so should_split = False
    assert percent_diff == 15.0
    assert should_split == False
    assert is_valid == True

    # Test small chunk (source_len < MIN_CHUNK_SIZE = 2000) - should NOT split
    is_valid, percent_diff, should_split = validate_translation_length(
        "x" * 1000, "x" * 1500, "test"  # 50% diff but source < MIN_CHUNK_SIZE
    )
    # should_split = False because source_len < MIN_CHUNK_SIZE
    assert percent_diff == 50.0
    assert should_split == False
    assert is_valid == True
