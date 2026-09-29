"""process_image_request must reach the images client and return a JPEG."""
import base64
import io
import os
import sys
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.utils as utils


def _png(mode, size=(40, 60)):
    buf = io.BytesIO()
    Image.new(mode, size, (200, 30, 30, 128) if mode == 'RGBA' else (200, 30, 30)).save(buf, format='PNG')
    return buf.getvalue()


class FakeImages:
    def __init__(self, result_png):
        self.result = base64.b64encode(result_png).decode()
        self.calls = []

    def create_variation(self, **kwargs):
        self.calls.append(('variation', kwargs))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.result)])

    def generate(self, **kwargs):
        self.calls.append(('generate', kwargs))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self.result)])


def _run(monkeypatch, result_png, metadata=None):
    images = FakeImages(result_png)
    monkeypatch.setattr(utils.llm_service, '_images_client', SimpleNamespace(images=images))
    source = base64.b64encode(_png('RGB')).decode()
    return utils.process_image_request(source, 'english', 'russian', 'Россия', metadata=metadata), images


def test_variation_of_the_existing_cover(monkeypatch):
    result, images = _run(monkeypatch, _png('RGB', (1024, 1024)))
    assert [c[0] for c in images.calls] == ['variation']
    data = base64.b64decode(result)
    assert data.startswith(b'\xff\xd8\xff')                 # JPEG
    assert Image.open(io.BytesIO(data)).size == (1024, 1536)


def test_rgba_result_from_the_image_model_is_saved_as_jpeg(monkeypatch):
    result, _ = _run(monkeypatch, _png('RGBA', (1024, 1024)))
    assert result is not None
    assert base64.b64decode(result).startswith(b'\xff\xd8\xff')


def test_generation_from_metadata(monkeypatch):
    result, images = _run(monkeypatch, _png('RGB'), metadata={'book-title': 'T', 'author': [], 'genre': []})
    assert [c[0] for c in images.calls] == ['generate']
    assert result is not None
