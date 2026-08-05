"""A4: creating a new dictionary must not raise AttributeError."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from src.vocabulary_manager import VocabularyManager, DictionaryCreatedSignal


def test_initialize_new_dictionary_no_attribute_error(tmp_path):
    book = tmp_path / "TestBook.fb2"
    book.write_text("<FictionBook></FictionBook>", encoding="utf-8")
    vm = VocabularyManager(str(book))
    vm._create_dictionary = lambda: None
    with pytest.raises(DictionaryCreatedSignal):
        vm.initialize()
