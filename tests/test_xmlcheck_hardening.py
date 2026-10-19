"""DEF-C6: XMLParser hardening for untrusted FB2 input.

The parser must never resolve entities (XXE / entity expansion) while still
accepting valid books whose <binary> payloads exceed lxml's default text-node
limit (~10 MB), which triggered false-positive "Resource limit exceeded".
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.xmlcheck as xc


XML_DECL = '<?xml version="1.0" encoding="utf-8"?>\n'

BODY_TEMPLATE = (
    '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
    '<description><title-info><genre>prose_classic</genre>'
    '<author><first-name>Test</first-name><last-name>Author</last-name></author>'
    '<book-title>{title}</book-title><lang>en</lang></title-info>'
    '<document-info><author><nickname>t</nickname></author>'
    '<date value="2024-01-01">2024</date><id>x-1</id><version>1.0</version></document-info>'
    '</description>'
    '<body><section><title><p>Ch</p></title><p>Text.</p></section></body>'
    '</FictionBook>'
)

MINI_BOOK = XML_DECL + BODY_TEMPLATE

MINI_WITH_DOCTYPE = XML_DECL + '<!DOCTYPE foo [{entities}]>\n' + BODY_TEMPLATE


def _book_with_binary(n_chars):
    payload = 'A' * n_chars
    return (
        XML_DECL +
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        '<description><title-info><genre>prose_classic</genre>'
        '<author><first-name>Test</first-name><last-name>Author</last-name></author>'
        '<book-title>Big Binary</book-title><lang>en</lang></title-info>'
        '<document-info><author><nickname>t</nickname></author>'
        '<date value="2024-01-01">2024</date><id>big-1</id><version>1.0</version></document-info>'
        '</description>'
        '<body><section><title><p>Ch</p></title><p>Text.</p></section></body>'
        '<binary id="big.png" content-type="image/png">' + payload + '</binary>'
        '</FictionBook>'
    )


def _book_with_entity(entities, title):
    return MINI_WITH_DOCTYPE.format(entities=entities, title=title)


def test_valid_book_with_11mb_binary_has_no_errors():
    """Valid FB2 with an ~11 MB <binary> must not hit the lxml text limit."""
    book = _book_with_binary(11_000_000)
    errors = xc.validate_fb2(book)
    assert errors == [], f"large but valid book rejected: {errors[:2]}"


def test_internal_entity_is_not_silently_expanded():
    """An entity in a valid book must be rejected, not silently expanded."""
    # Baseline: the same book without a DOCTYPE is valid.
    baseline = MINI_BOOK.format(title='Clean Title')
    assert xc.validate_fb2(baseline) == []

    book = _book_with_entity("<!ENTITY y 'ExpansionMarkerC6'>", '&y;')
    errors = xc.validate_fb2(book)
    joined = ' '.join(errors)
    assert errors, "document relying on entity expansion must not validate silently"
    assert 'ExpansionMarkerC6' not in joined


def test_external_entity_is_never_resolved():
    """XXE payload must produce errors without resolving file:// content."""
    book = _book_with_entity("<!ENTITY x SYSTEM 'file:///etc/passwd'>", '&x;')
    errors = xc.validate_fb2(book)
    joined = ' '.join(errors)
    assert errors, "XXE payload must not pass validation"
    assert 'root:' not in joined
    assert '/etc/passwd' not in joined
