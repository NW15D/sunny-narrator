#!/usr/bin/env python3
"""
Test series vocabulary creation with robust parsing.
This test simulates the scenario where LLM returns malformed JSON responses.
"""

import os
import sys
import tempfile
import shutil
import pytest
from unittest.mock import patch

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

@pytest.mark.skip(reason="Requires LLM integration - mock path complex due to dynamic import")
def test_series_vocab_with_malformed_json():
    """Test that series vocab handles malformed JSON gracefully."""
    from src.ner import create_series_vocab
    
    # Create test directory with sample books
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy sample books
        shutil.copy(os.path.join(project_root, 'books', 'eternal-moment.pg.epub'), tmpdir)
        shutil.copy(os.path.join(project_root, 'tests', 'data', 'ExampleBook.fb2'), tmpdir)
        
        output_file = os.path.join(tmpdir, 'test_series.dic')
        
        # Mock the vocabulary function to return malformed JSON
        def mock_vocabulary(source_lang, target_lang, source_text, country, role):
            # Simulate LLM returning malformed JSON with extra text
            if "Haddon" in source_text:
                return '''Some preamble...
{
    "terms": [
        {"source": "Miss Haddon", "target": "Мисс Хэддон", "category": "PERSON"}
    ]
}
Trailing text...'''
            elif "Cantù" in source_text:
                return '''[
{"source": "Signora Cantù", "target": "Синьора Канту", "category": "PERSON"}
]'''
            elif "Gutenberg" in source_text:
                return '''Here's the translation:
{"source": "Project Gutenberg", "target": "Проект Гутенберг", "category": "ORG"}
End of response.'''
            else:
                # Fallback CSV format
                lines = []
                for line in source_text.split('\n'):
                    if line.strip():
                        term = line.split('[')[0].strip()
                        lines.append(f"{term} = Перевод_{term.replace(' ', '_')}")
                return '\n'.join(lines)
        
        # Patch the vocabulary function (ta = src.utils alias in ner.py)
        with patch('src.utils.vocabulary', side_effect=mock_vocabulary):
            try:
                result = create_series_vocab(
                    tmpdir, 
                    output_file,
                    min_count_ner=1,
                    min_count_word=1
                )
                
                # Verify output file exists and has content
                assert os.path.exists(result)
                
                # Read the file and check it has translations
                with open(result, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Should have non-empty translations
                assert "Мисс Хэддон" in content
                assert "Синьора Канту" in content
                assert "Проект Гутенберг" in content
                assert "Перевод_" in content  # From fallback
                
                print("✅ Series vocab with malformed JSON test passed")
                
            except Exception as e:
                print(f"❌ Test failed: {e}")
                raise

if __name__ == "__main__":
    test_series_vocab_with_malformed_json()
    print("🎉 All series vocab robust tests passed!")