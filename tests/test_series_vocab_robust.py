#!/usr/bin/env python3
"""
Test series vocabulary creation with robust parsing.
This test simulates the scenario where LLM returns malformed JSON responses.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

def test_series_vocab_with_malformed_json():
    """Test that series vocab handles malformed JSON gracefully."""
    from src.ner import create_series_vocab
    
    # Create test directory with sample books
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy sample books
        shutil.copy(os.path.join(project_root, 'books', 'Cargo.fb2'), tmpdir)
        shutil.copy(os.path.join(project_root, 'books', 'ExampleBook.fb2'), tmpdir)
        
        output_file = os.path.join(tmpdir, 'test_series.dic')
        
        # Mock the vocabulary function to return malformed JSON
        def mock_vocabulary(source_lang, target_lang, source_text, country, role):
            # Simulate LLM returning malformed JSON with extra text
            if "BENJAMIN" in source_text:
                return '''Some preamble...
{
    "terms": [
        {"source": "BENJAMIN BABBAGE", "target": "БЕНДЖАМИН БЭББИДЖ", "category": "PERSON"}
    ]
}
Trailing text...'''
            elif "JANE" in source_text:
                return '''[
{"source": "JANE BERRENDT", "target": "ДЖЕЙН БЕРРЕНДТ", "category": "PERSON"}
]'''
            elif "Dallas" in source_text:
                return '''Here's the translation:
{"source": "Dallas", "target": "Даллас", "category": "GPE"}
End of response.'''
            else:
                # Fallback CSV format
                lines = []
                for line in source_text.split('\n'):
                    if line.strip():
                        term = line.split('[')[0].strip()
                        lines.append(f"{term} = Перевод_{term.replace(' ', '_')}")
                return '\n'.join(lines)
        
        # Patch the vocabulary function
        with patch('src.ner.ta.vocabulary', side_effect=mock_vocabulary):
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
                assert "БЕНДЖАМИН БЭББИДЖ" in content
                assert "ДЖЕЙН БЕРРЕНДТ" in content
                assert "Даллас" in content
                assert "Перевод_" in content  # From fallback
                
                print("✅ Series vocab with malformed JSON test passed")
                
            except Exception as e:
                print(f"❌ Test failed: {e}")
                raise

if __name__ == "__main__":
    test_series_vocab_with_malformed_json()
    print("🎉 All series vocab robust tests passed!")