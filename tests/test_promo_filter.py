from src.calibre_pipeline import _sanitize_source_html, extract_metadata_from_opf  # noqa
from src.promo_filter import html_to_paragraphs, html_to_text, strip_promo_markup, strip_promo_text


def test_escaped_html_description_becomes_plain_text():
    raw = '&lt;div&gt;&lt;p&gt;First &lt;strong&gt;bold&lt;/strong&gt; &amp;amp; more&lt;/p&gt;&lt;p&gt;Second&lt;/p&gt;&lt;/div&gt;'
    assert html_to_paragraphs(raw) == ['First bold & more', 'Second']
    assert html_to_text(raw) == 'First bold & more Second'


def test_plain_description_untouched():
    assert html_to_paragraphs('Just text') == ['Just text']


def test_opf_description_has_no_tags():
    opf = '<dc:description>&lt;div&gt;&lt;p&gt;Hi &lt;strong&gt;there&lt;/strong&gt;&lt;/p&gt;&lt;/div&gt;</dc:description>'
    assert extract_metadata_from_opf(opf)['description'] == 'Hi there'


def test_strip_promo_text():
    assert strip_promo_text('Hello oceanofpdf.com world').split() == ['Hello', 'world']
    assert 'oceanofpdf' not in strip_promo_text('Downloaded from https://oceanofpdf.com/x\nText')
    assert strip_promo_text('Plain text.') == 'Plain text.'


def test_strip_promo_markup_keeps_structure():
    out = strip_promo_markup('<p>Real.</p><p><a href="https://oceanofpdf.com">OceanofPDF.com</a></p><p>More oceanofpdf.com text</p>')
    assert 'oceanofpdf' not in out.lower()
    assert out.startswith('<p>Real.</p>') and '<p>More' in out


def test_sanitize_source_html_drops_promo(monkeypatch):
    import logging
    from src import calibre_pipeline
    monkeypatch.setattr(calibre_pipeline, 'logger', logging.getLogger('t'))
    out = _sanitize_source_html('<p>Text</p><div><a href="https://oceanofpdf.com/">oceanofpdf.com</a></div>')
    assert 'oceanofpdf' not in out and 'Text' in out
