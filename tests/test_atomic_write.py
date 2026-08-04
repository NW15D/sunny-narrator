"""Test atomic write safety for vocabulary_manager.py"""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_vocab_atomic_write():
    """Verify that if os.replace fails mid-write, original file is intact."""
    from vocabulary_manager import VocabularyManager
    
    # Create a temp directory and dict file with known content
    with tempfile.TemporaryDirectory() as tmpdir:
        dict_file = os.path.join(tmpdir, 'test.dic')
        original_content = "# Original dictionary\nAlice = Алиса | PERSON | | \n"
        
        # Write original file
        with open(dict_file, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # Create VocabularyManager with mocked dependencies
        vm = VocabularyManager.__new__(VocabularyManager)
        vm.dict_file = dict_file
        vm.book_name = "Test Book"
        vm.vocab = {}
        
        # Mock os.replace to simulate crash/disk-full
        with patch('os.replace', side_effect=OSError("Disk full")):
            try:
                vm._atomic_write("# New content that should NOT be saved\n")
                assert False, "Should have raised OSError"
            except OSError:
                pass
        
        # Verify original file is intact
        with open(dict_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert content == original_content, f"Original file was corrupted! Got: {content!r}"
        
        # Verify temp file was cleaned up
        tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
        assert len(tmp_files) == 0, f"Temp files not cleaned up: {tmp_files}"


def test_vocab_atomic_write_success():
    """Verify atomic write works correctly on success."""
    from vocabulary_manager import VocabularyManager
    
    with tempfile.TemporaryDirectory() as tmpdir:
        dict_file = os.path.join(tmpdir, 'test.dic')
        
        vm = VocabularyManager.__new__(VocabularyManager)
        vm.dict_file = dict_file
        vm.book_name = "Test Book"
        vm.vocab = {}
        
        new_content = "# New dictionary\nBob = Боб | PERSON | | \n"
        vm._atomic_write(new_content)
        
        with open(dict_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert content == new_content


def test_parse_and_save_atomic():
    """Verify _parse_and_save uses atomic write."""
    from vocabulary_manager import VocabularyManager
    
    with tempfile.TemporaryDirectory() as tmpdir:
        dict_file = os.path.join(tmpdir, 'test.dic')
        
        vm = VocabularyManager.__new__(VocabularyManager)
        vm.dict_file = dict_file
        vm.book_name = "Test Book"
        vm.vocab = {}
        
        # Mock _atomic_write to verify it's called
        with patch.object(vm, '_atomic_write') as mock_atomic:
            vm._parse_and_save("Alice = Алиса (PERSON)")
            mock_atomic.assert_called_once()
            # Verify content passed to _atomic_write
            content = mock_atomic.call_args[0][0]
            assert "Alice = Алиса" in content
            assert "# Vocabulary for Test Book" in content


def test_create_template_atomic():
    """Verify _create_template uses atomic write."""
    from vocabulary_manager import VocabularyManager
    
    with tempfile.TemporaryDirectory() as tmpdir:
        dict_file = os.path.join(tmpdir, 'test.dic')
        
        vm = VocabularyManager.__new__(VocabularyManager)
        vm.dict_file = dict_file
        vm.book_name = "Test Book"
        vm.vocab = {}
        
        with patch.object(vm, '_atomic_write') as mock_atomic:
            vm._create_template()
            mock_atomic.assert_called_once()
            content = mock_atomic.call_args[0][0]
            assert "# Vocabulary for Test Book" in content


if __name__ == '__main__':
    test_vocab_atomic_write()
    test_vocab_atomic_write_success()
    test_parse_and_save_atomic()
    test_create_template_atomic()
    print("All atomic write tests passed!")
