
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src import fb2_handler
from src import utils
from src.config import Config

class TestCoverFlow(unittest.TestCase):

    def setUp(self):
        self.header_with_cover = """
<description>
    <title-info>
        <book-title>Test Book</book-title>
        <coverpage>
            <image l:href="#cover.jpg"/>
        </coverpage>
    </title-info>
</description>
"""
        self.footer_with_cover = """
<binary id="cover.jpg" content-type="image/jpeg">BASE64DATA</binary>
"""
        self.body = "<body><section><p>Text</p></section></body>"

    def test_get_cover_image(self):
        data = fb2_handler.get_cover_image(self.header_with_cover, self.footer_with_cover)
        self.assertEqual(data, "BASE64DATA")

    def test_get_cover_image_not_found(self):
        header = "<description></description>"
        data = fb2_handler.get_cover_image(header, self.footer_with_cover)
        self.assertIsNone(data)

    def test_replace_cover_image_with_image(self):
        new_image = "REPLACED_DATA" * 10  # Make it long enough > 100 chars
        h, f, b = fb2_handler.replace_cover_image(
            self.header_with_cover, self.footer_with_cover, self.body, new_image
        )
        self.assertIn("REPLACED_DATA", f)
        self.assertNotIn("BASE64DATA", f)
        self.assertIn('id="cover.jpg"', f) # ID should be preserved

    def test_replace_cover_image_with_text(self):
        new_text = "This is a description of the cover."
        h, f, b = fb2_handler.replace_cover_image(
            self.header_with_cover, self.footer_with_cover, self.body, new_text
        )
        # Header should not have coverpage
        self.assertNotIn("<coverpage>", h)
        # Footer should not have binary
        self.assertNotIn("<binary", f)
        # Body should have text
        self.assertIn("This is a description of the cover.", b)
        self.assertIn("<section>", b)

    @patch('src.utils.clientc')
    def test_process_image_request(self, mock_client):
        # Mock response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Cover Description"
        mock_client.chat.completions.create.return_value = mock_response

        # Need to mock config values since they are used in function
        # utils.config is global, so we might need to patch it or set env vars.
        # But utils.py instantiates Config() at import time.
        # We can patch config in utils
        
        with patch('src.utils.config') as mock_config:
            mock_config.sys_not_promt3 = False
            mock_config.model3 = "gpt-4-vision"
            mock_config.temp3 = 0.5
            mock_config.max_len_chunk = 100
            
            result = utils.process_image_request("DATA", "Prompt")
            self.assertEqual(result, "Cover Description")
            
            # Verify call args
            calls = mock_client.chat.completions.create.call_args
            self.assertTrue(calls)

if __name__ == '__main__':
    unittest.main()
