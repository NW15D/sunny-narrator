"""F6 count-guard: language-agnostic heading counting + source/translation parity.

Headings are recognised only by Markdown syntax (a line starting with
1-6 '#' followed by whitespace, after normalize_markdown_headings) — no
word lists, no language-specific titles. Fixtures stay ASCII on purpose.
"""
import logging

from src.calibre_pipeline import check_heading_parity, count_markdown_headings

MODULE_LOGGER = "src.calibre_pipeline"


def test_counts_headings_by_level():
    text = (
        "Opening paragraph.\n\n"
        "# Heading 1\n\n"
        "Body.\n\n"
        "## Heading 2\n\n"
        "### Heading 3\n\n"
        "#### Heading 4\n\n"
        "##### Heading 5\n\n"
        "###### Heading 6\n\n"
        "####### Seven hashes is not a heading.\n"
    )
    assert count_markdown_headings(text) == [
        "# Heading 1",
        "## Heading 2",
        "### Heading 3",
        "#### Heading 4",
        "##### Heading 5",
        "###### Heading 6",
    ]


def test_no_headings_and_empty_input():
    assert count_markdown_headings("") == []
    assert count_markdown_headings("Just a paragraph.\nAnother line.\n") == []
    # '#' mid-line is not a heading: the pattern is anchored at line start
    assert count_markdown_headings("Body text.# Heading 2\n") == []


def test_glued_hash_is_normalized_before_counting():
    # normalize_markdown_headings turns '#Heading 2' into '# Heading 2'
    assert count_markdown_headings("prose\n#Heading 2\n") == ["# Heading 2"]


def test_lost_heading_warns_with_line(caplog):
    source = "# (23)\n\nA paragraph.\n"
    translated = "A paragraph, translated.\n"
    with caplog.at_level(logging.WARNING, logger=MODULE_LOGGER):
        lost, added = check_heading_parity(source, translated)
    assert lost == ["# (23)"]
    assert added == []
    messages = [r.getMessage() for r in caplog.records if r.name == MODULE_LOGGER]
    assert any("# (23)" in m for m in messages)


def test_matching_level_counts_do_not_warn(caplog):
    source = "# Heading 1\n\nA paragraph.\n\n## Heading 2\n"
    translated = "# Translated title\n\nA paragraph, translated.\n\n## Translated section\n"
    with caplog.at_level(logging.WARNING, logger=MODULE_LOGGER):
        lost, added = check_heading_parity(source, translated)
    assert lost == []
    assert added == []
    module_warnings = [
        r for r in caplog.records
        if r.name == MODULE_LOGGER and r.levelno >= logging.WARNING
    ]
    assert module_warnings == []


def test_extra_heading_reported_as_added():
    source = "# Heading 1\n\nA paragraph.\n"
    translated = "# Heading 1\n\nA paragraph.\n\n## Extra invented section\n"
    lost, added = check_heading_parity(source, translated)
    assert lost == []
    assert added == ["## Extra invented section"]
