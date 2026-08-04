"""F2: FictionBook XSD schema is parsed once and cached."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import xmlcheck


def test_xsd_schema_cached_across_calls():
    schema1, path1 = xmlcheck._get_fb2_schema()
    schema2, path2 = xmlcheck._get_fb2_schema()
    assert schema1 is not None, f"Schema not loaded from {path1}"
    assert path1 == path2
    assert schema1 is schema2
    # validate_fb2 works through the cached schema (invalid input -> error list, no crash)
    errors = xmlcheck.validate_fb2("<not-fb2/>")
    assert isinstance(errors, list)
    assert errors  # non-FB2 document must fail schema validation
