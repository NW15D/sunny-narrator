"""Text-mode reflection: lines whose X is not in the translation are dropped
(the improve stage cannot apply them), like the JSON fixes."""
from src.utils import _keep_applicable_lines

TR = "Мара открыл дверь. Тобиас ждала в коридоре."


def test_keeps_applicable_lines_with_and_without_guillemets():
    text = "Мара открыл → Мара открыла — род\\n«ждала» → «ждал» — род"
    assert _keep_applicable_lines(text.replace("\\n", "\n"), TR, "russian").count("→") == 2


def test_drops_absent_find_and_noop_lines():
    text = "Мара открыла → Мара открыла дверь — нет такого\nждала → ждала — ничего\nждала → ждал — род"
    assert _keep_applicable_lines(text, TR, "russian") == "ждала → ждал — род"


def test_no_changes_when_every_line_is_dropped():
    assert _keep_applicable_lines("нет такого → есть — причина", TR, "russian") == "NO CHANGES"


def test_other_shapes_pass_through():
    assert _keep_applicable_lines("NO CHANGES", TR, "russian") == "NO CHANGES"
    assert _keep_applicable_lines("общее замечание", TR, "russian") == "общее замечание"
