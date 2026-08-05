"""C6: UTF-8 BOM must not leak into parsed content (TXT and FB2)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.txt_handler import parse_txt
from src.fb2_handler import parse_xml


def test_txt_bom_not_in_content(tmp_path):
    p = tmp_path / 'bom.txt'
    p.write_bytes('Первый абзац.\nВторой абзац.'.encode('utf-8-sig'))
    body, header, footer = parse_txt(str(p))
    assert '\ufeff' not in body
    assert '\ufeff' not in header


def test_fb2_bom_not_in_output(tmp_path):
    fb2 = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        '<description><title-info><book-title>T</book-title></title-info></description>'
        '<body><section><p>Текст.</p></section></body>'
        '</FictionBook>'
    )
    p = tmp_path / 'bom.fb2'
    p.write_bytes(fb2.encode('utf-8-sig'))
    body, header, footer = parse_xml(str(p))
    assert '\ufeff' not in header
    assert '\ufeff' not in body
