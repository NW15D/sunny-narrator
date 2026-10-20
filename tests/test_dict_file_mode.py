"""A rewritten .dic keeps the mode of the original instead of mkstemp's 0600."""
import os
import stat

from src.vocabulary_manager import restore_file_mode


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_existing_target_mode_is_kept(tmp_path):
    target = tmp_path / "book_ru.dic"
    target.write_text("a = b\n")
    os.chmod(target, 0o640)
    tmp = tmp_path / "x.tmp"
    tmp.write_text("c = d\n")
    os.chmod(tmp, 0o600)
    restore_file_mode(str(tmp), str(target))
    assert _mode(tmp) == 0o640


def test_new_target_gets_umask_default(tmp_path):
    tmp = tmp_path / "x.tmp"
    tmp.write_text("c = d\n")
    os.chmod(tmp, 0o600)
    umask = os.umask(0)
    os.umask(umask)
    restore_file_mode(str(tmp), str(tmp_path / "missing.dic"))
    assert _mode(tmp) == 0o666 & ~umask
