"""B6/C10: pipeline must fail when output validation fails."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


def test_enforce_validation_raises_on_errors():
    from src.calibre_pipeline import _enforce_validation, ValidationReport
    report = ValidationReport(is_valid=False, file_path='/tmp/x.epub', format='epub')
    report.add_issue('error', 'broken spine')
    with pytest.raises(RuntimeError):
        _enforce_validation(report, allow_invalid=False)
    # allow_invalid=True must not raise
    _enforce_validation(report, allow_invalid=True)
    ok_report = ValidationReport(is_valid=True, file_path='/tmp/y.epub', format='epub')
    _enforce_validation(ok_report, allow_invalid=False)
