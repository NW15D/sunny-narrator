"""
Test: Resume from checkpoint must not lose previously-translated sections.

Bug: On partial resume, `chunks = chunks[resume_from_chunk:]` slices away
already-translated chunks. `process_all_chunks` returns ONLY new content.
The final assembly loses all prior sections.

Fix: `assemble_resume_content()` reads the full output_tfile (which has
prior + new sections appended) when resuming.
"""

import os
import tempfile
import pytest

# Import the function under test
from app import assemble_resume_content


class TestResumeIntegrity:
    """Verify that resuming from checkpoint preserves all translated content."""

    def test_resume_returns_full_content_from_tfile(self):
        """When resuming (resume_from_chunk > 0), the result must contain
        ALL sections from output_tfile, not just the new ones."""
        prior_sections = (
            "<section>\n<p>Prior section 1 translated</p>\n</section>\n"
            "<section>\n<p>Prior section 2 translated</p>\n</section>\n"
        )
        new_sections = (
            "<section>\n<p>New section 3 translated</p>\n</section>\n"
        )
        # output_tfile accumulates ALL sections (prior + new) via append mode
        full_content = prior_sections + new_sections

        with tempfile.NamedTemporaryFile(mode='w', suffix='.fb2', delete=False, encoding='utf-8') as f:
            f.write(full_content)
            tfile_path = f.name

        try:
            # process_all_chunks only returns new content on resume
            result = assemble_resume_content(
                new_content=new_sections,
                resume_from_chunk=2,  # Resuming from chunk 2 (0-indexed)
                output_tfile=tfile_path,
            )
            # Must contain ALL sections, not just new ones
            assert "Prior section 1 translated" in result, \
                "FAIL: Prior section 1 lost on resume!"
            assert "Prior section 2 translated" in result, \
                "FAIL: Prior section 2 lost on resume!"
            assert "New section 3 translated" in result, \
                "FAIL: New section 3 missing!"
        finally:
            os.unlink(tfile_path)

    def test_fresh_run_returns_new_content(self):
        """On a fresh run (resume_from_chunk == 0), return new_content as-is."""
        new_content = "<section>\n<p>First section</p>\n</section>\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.fb2', delete=False, encoding='utf-8') as f:
            f.write(new_content)
            tfile_path = f.name

        try:
            result = assemble_resume_content(
                new_content=new_content,
                resume_from_chunk=0,
                output_tfile=tfile_path,
            )
            assert result == new_content
        finally:
            os.unlink(tfile_path)

    def test_resume_without_tfile_returns_new_content(self):
        """If output_tfile doesn't exist on resume, fall back to new_content."""
        result = assemble_resume_content(
            new_content="<section>\n<p>Only new</p>\n</section>\n",
            resume_from_chunk=3,
            output_tfile="/nonexistent/path/file.fb2",
        )
        assert result == "<section>\n<p>Only new</p>\n</section>\n"

    def test_resume_all_sections_present_in_order(self):
        """Sections must appear in correct order: prior first, then new."""
        sections = []
        for i in range(1, 6):
            sections.append(f"<section>\n<p>Section {i}</p>\n</section>\n")
        full_content = "".join(sections)

        # Simulate: chunks 0-2 done (sections 1-3), resuming from chunk 3
        new_content = "".join(sections[3:])  # sections 4-5 only

        with tempfile.NamedTemporaryFile(mode='w', suffix='.fb2', delete=False, encoding='utf-8') as f:
            f.write(full_content)
            tfile_path = f.name

        try:
            result = assemble_resume_content(
                new_content=new_content,
                resume_from_chunk=3,
                output_tfile=tfile_path,
            )
            # All 5 sections must be present
            for i in range(1, 6):
                assert f"Section {i}" in result, f"FAIL: Section {i} lost!"
            # Order must be preserved
            pos = [result.index(f"Section {i}") for i in range(1, 6)]
            assert pos == sorted(pos), "FAIL: Section order corrupted!"
        finally:
            os.unlink(tfile_path)
