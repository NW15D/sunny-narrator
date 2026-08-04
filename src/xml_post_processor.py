"""
XML Post-Processor for Sunny Narrator.

Handles XML cleanup and tag-repair after translation.
Extracted from TranslationEngine in app.py.
"""

import re
import time
import logging
import src.utils as ta

logger = logging.getLogger(__name__)


class XmlPostProcessor:
    """Processes and repairs XML content after translation."""

    def __init__(self, config):
        """
        Initialize the XML post-processor.

        Args:
            config: Configuration object with source_lang, target_lang,
                    model_proofread, llm_repair_max_tokens attributes.
        """
        self.config = config

    def post_process(self, source_text: str, translated_text: str) -> str:
        """
        Basic XML cleanup after translation.

        NOTE: Does NOT repair tag structure for chunks.
        Chunks may have intentionally unbalanced tags
        (e.g., <title> opened in one chunk, closed in another).
        Full XML validation happens only on final assembled document.

        - Removes artifacts via rem_tags()
        - Does NOT use LLM repair (would break chunk structure)
        """
        # Basic cleanup only - no XML parsing of chunks
        # rem_tags is for final FB2 validation, not chunk processing
        cleaned = translated_text.strip()

        # Remove common artifacts
        cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)

        return cleaned

    def repair_xml(self, source_text: str, translated_text: str) -> str:
        """
        Repair lost XML tags using LLM with 1 retry.

        Args:
            source_text: Original source text with correct XML tags.
            translated_text: Translated text that may have lost XML tags.

        Returns:
            Repaired translated text, or original if repair fails.
        """
        prompt = f"""ОРИГИНАЛ ({self.config.source_lang}):
{source_text[:1000]}

ПЕРЕВОД ({self.config.target_lang}, могут быть потеряны тэги):
{translated_text[:1000]}

ЗАДАЧА: Восстанови XML-тэги FB2 (<p>, </p>, <strong>, <em>, etc.) в переводе.
Верни ТОЛЬКО исправленный перевод с тэгами."""

        max_tokens = getattr(self.config, 'llm_repair_max_tokens', 2000)
        # The prompt above truncates both inputs to 1000 chars
        truncated_input = len(source_text) > 1000 or len(translated_text) > 1000

        for attempt in range(2):  # 1 initial + 1 retry
            try:
                # Safe getattr: avoid eager evaluation of default arg
                client = getattr(ta.llm_service, 'clientProofread', None)
                if client is None:
                    client = getattr(ta.llm_service, '_secondary_client', None)
                if client is None:
                    client = getattr(ta.llm_service, 'clientTranslate', None)
                if client is None:
                    client = getattr(ta.llm_service, '_primary_client', None)
                if client is None:
                    raise AttributeError("LLMService has no usable client attribute")
                response = client.chat.completions.create(
                    model=self.config.model_proofread,
                    messages=[
                        {"role": "system", "content": "Ты редактор XML. Восстанавливай тэги FB2."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=max_tokens
                )
                result = response.choices[0].message.content
                # Guard: with a truncated prompt the LLM only sees a prefix.
                # If its answer is shorter than the full translation, using it
                # would silently drop the tail — keep the original text.
                if truncated_input and len(result.strip()) < len(translated_text.strip()):
                    logger.warning(
                        "repair_xml: prompt was truncated and LLM result is shorter "
                        "than the full translation — keeping original to avoid content loss"
                    )
                    return translated_text
                return result
            except Exception as e:
                logger.error(f"LLM repair attempt {attempt + 1} failed ({type(e).__name__}): {e}")
                if attempt == 0:
                    time.sleep(1)  # Brief pause before retry

        logger.warning("LLM repair exhausted all retries, returning original text")
        return translated_text

    def count_tags(self, text: str) -> dict:
        """
        Count XML tags in text.

        Args:
            text: Text to scan for XML tags.

        Returns:
            Dictionary mapping tag strings to their occurrence counts.
        """
        tags = re.findall(r'</?[a-zA-Z][^>]*>', text)
        counts = {}
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
        return counts

    def tag_difference(self, source_tags: dict, translated_tags: dict) -> float:
        """
        Calculate tag difference ratio (0.0-1.0).

        Args:
            source_tags: Tag counts from source text (from count_tags).
            translated_tags: Tag counts from translated text (from count_tags).

        Returns:
            Float ratio representing tag mismatch severity.
            0.0 = identical tags, 1.0 = completely different.
        """
        all_tags = set(source_tags.keys()) | set(translated_tags.keys())
        if not all_tags:
            return 0.0

        diffs = []
        for tag in all_tags:
            src = source_tags.get(tag, 0)
            trans = translated_tags.get(tag, 0)
            if src > 0:
                diffs.append(abs(src - trans) / src)

        return sum(diffs) / len(diffs) if diffs else 0.0
