"""Tests for structural-block-aware markdown chunking.

Covers parse_structural_blocks / merge_blocks_to_chunks / split_markdown_structured:
- fences, list markers, table rows, blockquote prefixes never split across chunks
- blockquote with internal '>' blank lines stays one block
- chunks are non-empty and eventually cover all content
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.markdown_utils import (
    parse_structural_blocks,
    split_markdown_structured,
)


def test_parse_blockquote_with_internal_gt_lines_stays_one_block():
    """'<quote> line\n>\n<quote> line' must be a single blockquote block."""
    md = "> line 1\n>\n> line 2"
    blocks = parse_structural_blocks(md)
    assert len(blocks) == 1, f"Expected 1 block, got {len(blocks)}"
    assert blocks[0][1] == 'blockquote'
    assert '> line 1' in blocks[0][0]
    assert '> line 2' in blocks[0][0]


def test_parse_blank_line_separates_blockquotes():
    """A truly blank line between quotes starts a new blockquote."""
    md = "> quote 1\n\n> quote 2"
    blocks = parse_structural_blocks(md)
    quotes = [b for b in blocks if b[1] == 'blockquote']
    assert len(quotes) == 2, f"Expected 2 blockquotes, got {len(quotes)}"


def test_parse_code_fence_never_splits():
    """Fenced code block with blank lines inside must stay one block."""
    md = "```python\n\ndef f():\n\n    return 1\n\n```"
    blocks = parse_structural_blocks(md)
    assert len(blocks) == 1, f"Expected 1 code block, got {len(blocks)}"
    assert blocks[0][1] == 'code_block'


def test_parse_table_rows_grouped():
    """Consecutive table rows form a single table block."""
    md = "| a | b |\n|---|---|\n| 1 | 2 |"
    blocks = parse_structural_blocks(md)
    tables = [b for b in blocks if b[1] == 'table']
    assert len(tables) == 1
    assert '| a | b |' in tables[0][0]
    assert '| 1 | 2 |' in tables[0][0]


def test_split_keeps_code_fence_intact():
    """A code block larger than target must not split mid-fence."""
    md = "```python\n" + "x = 1\n" * 50 + "```"
    chunks = split_markdown_structured(md, target_size=100)
    assert len(chunks) >= 1
    for chunk in chunks:
        # Every chunk must contain a balanced fence (0 or 2 fences)
        assert chunk.count('```') % 2 == 0, f"Unbalanced fence in chunk: {chunk[:40]}..."


def test_split_keeps_blockquote_prefix():
    """Blockquote lines must not lose their '>' prefix across chunks."""
    md = "> " + "word " * 300
    chunks = split_markdown_structured(md, target_size=200)
    for chunk in chunks:
        for line in chunk.split('\n'):
            if line.strip():
                assert line.lstrip().startswith('>'), f"Lost '>' prefix: {line[:40]}"


def test_split_keeps_list_markers():
    """List items must keep their -/*/+ markers after chunking."""
    md = "- item one\n- item two\n- " + "long " * 300 + "\n- item four"
    chunks = split_markdown_structured(md, target_size=200)
    for chunk in chunks:
        for line in chunk.split('\n'):
            if line.strip() and not line.startswith(' '):
                assert line.startswith('- '), f"Lost list marker: {line[:40]}"


def test_split_keeps_heading_line():
    """A heading must never be split away from its own line."""
    md = "# Chapter " + "x" * 200 + "\n\nbody text " + "y" * 200
    chunks = split_markdown_structured(md, target_size=100)
    for chunk in chunks:
        lines = chunk.split('\n')
        for line in lines:
            if line.startswith('# '):
                assert len(line.strip()) > 10, f"Heading truncated: {line[:40]}"


def test_split_merges_small_blocks():
    """Small adjacent blocks should merge into fewer chunks."""
    md = "para one\n\npara two\n\npara three"
    chunks = split_markdown_structured(md, target_size=1000)
    assert len(chunks) == 1, f"Expected 1 merged chunk, got {len(chunks)}"


def test_split_empty_and_short_inputs():
    """Empty and short inputs return as-is."""
    assert split_markdown_structured("") == []
    assert split_markdown_structured("   ") == []
    short = "tiny text"
    assert split_markdown_structured(short, target_size=1000) == [short]