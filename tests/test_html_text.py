from src.calibre_pipeline import extract_metadata_from_opf
from src.html_text import html_to_paragraphs, html_to_text


def test_escaped_html_description_becomes_plain_text():
    raw = '&lt;div&gt;&lt;p&gt;First &lt;strong&gt;bold&lt;/strong&gt; &amp;amp; more&lt;/p&gt;&lt;p&gt;Second&lt;/p&gt;&lt;/div&gt;'
    assert html_to_paragraphs(raw) == ['First bold & more', 'Second']
    assert html_to_text(raw) == 'First bold & more Second'


def test_plain_description_untouched():
    assert html_to_paragraphs('Just text') == ['Just text']


def test_opf_description_has_no_tags():
    opf = '<dc:description>&lt;div&gt;&lt;p&gt;Hi &lt;strong&gt;there&lt;/strong&gt;&lt;/p&gt;&lt;/div&gt;</dc:description>'
    assert extract_metadata_from_opf(opf)['description'] == 'Hi there'


def test_no_break_spaces_collapse():
    assert html_to_paragraphs('<p>a  b</p>') == ['a b']
