"""
F4/F5 v1 report: the run's metrics carry the foreign words of the stages
and the largest count of mixed-alphabet words after final_edit; a count
above MIXED_WORDS_FINAL_EDIT_WARN (default 10) logs a WARNING. The gate
is report-only: nothing here blocks or retries a translation.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import utils


class _Recorder:
    """Stands in for the module logger: keeps (level, message) of each line."""

    def __init__(self):
        self.lines = []

    def _log(self, level, msg, *args):
        self.lines.append((level, (msg % args) if args else str(msg)))

    def debug(self, msg, *args, **kwargs):
        self._log('debug', msg, *args)

    def info(self, msg, *args, **kwargs):
        self._log('info', msg, *args)

    def warning(self, msg, *args, **kwargs):
        self._log('warning', msg, *args)

    def error(self, msg, *args, **kwargs):
        self._log('error', msg, *args)


def _fresh(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(utils, 'logger', rec)
    return utils.TranslationMetrics(), rec


def test_foreign_words_reach_the_report(monkeypatch):
    metrics, rec = _fresh(monkeypatch)
    metrics.log_foreign_words(['dazhe', 'desyatki'], 'improve_translation')
    assert metrics.foreign_words == 2
    assert metrics.get_report()['foreign_words'] == 2
    warnings = [t for lvl, t in rec.lines if lvl == 'warning']
    assert any('dazhe' in t and 'improve_translation' in t for t in warnings)


def test_mixed_words_after_final_edit_reach_the_report(monkeypatch):
    metrics, rec = _fresh(monkeypatch)
    metrics.log_mixed_words(['d\u043e\u0448\u043b\u043e'])
    metrics.log_mixed_words_final(12)
    assert metrics.mixed_words == 1
    assert metrics.mixed_words_final == 12
    report = metrics.get_report()
    assert report['mixed_words'] == 1
    assert report['mixed_words_final'] == 12
    warnings = [t for lvl, t in rec.lines if lvl == 'warning']
    assert any('after final_edit' in t and '12' in t for t in warnings)


def test_final_edit_count_at_the_threshold_is_not_a_warning(monkeypatch):
    metrics, rec = _fresh(monkeypatch)
    assert utils.MIXED_WORDS_FINAL_EDIT_WARN == 10
    metrics.log_mixed_words_final(utils.MIXED_WORDS_FINAL_EDIT_WARN)
    assert metrics.mixed_words_final == 10
    assert not [t for lvl, t in rec.lines if lvl == 'warning']


def test_the_report_keeps_the_largest_final_edit_count(monkeypatch):
    metrics, rec = _fresh(monkeypatch)
    metrics.log_mixed_words_final(3)
    metrics.log_mixed_words_final(12)
    metrics.log_mixed_words_final(1)
    assert metrics.mixed_words_final == 12


def test_print_report_carries_the_new_lines(monkeypatch):
    metrics, rec = _fresh(monkeypatch)
    metrics.log_foreign_words(['tela'], 'final_edit')
    metrics.print_report()
    text = '\n'.join(t for _, t in rec.lines)
    assert 'Foreign words (other alphabet): 1' in text
    assert 'after final_edit: 0' in text
