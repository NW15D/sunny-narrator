"""C7: synopsis must be generated from the FINAL translation, not the draft."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import src.utils as u


def test_synopsis_uses_final_translation(monkeypatch):
    p = u.TranslationPipeline()

    def mk(text):
        return u.TranslationResult(
            stage=u.TranslationStage.FINAL,
            llm_role=u.LLMRole.PRIMARY,
            text=text,
            metadata={}
        )

    monkeypatch.setattr(p, 'initial_translation', lambda ctx: mk('DRAFT'))
    monkeypatch.setattr(p, 'reflection', lambda ctx, txt: mk('REFLECTION'))
    monkeypatch.setattr(p, 'improve_translation', lambda ctx, txt, refl: mk('IMPROVED'))
    monkeypatch.setattr(p, 'final_edit', lambda ctx, txt: mk('FINAL-EDIT-TEXT'))

    seen = {}

    def fake_synopsis(ctx, text):
        seen['text'] = text
        return u.TranslationResult(
            stage=u.TranslationStage.SYNOPSIS,
            llm_role=u.LLMRole.PRIMARY,
            text='SYNOPSIS',
            metadata={}
        )

    monkeypatch.setattr(p, 'generate_synopsis', fake_synopsis)

    p.execute(
        source_lang='en', target_lang='ru', source_text='hello world',
        outline_text='', vocab_dict={}, vocab_entries=[],
        country='', style='text', fast_mode=False
    )

    assert seen.get('text') == 'FINAL-EDIT-TEXT'


def test_synopsis_works_in_fast_mode(monkeypatch):
    """fast_mode: final_edit_result не существует — synopsis строится от final_result."""
    p = u.TranslationPipeline()

    def mk(text):
        return u.TranslationResult(
            stage=u.TranslationStage.FINAL,
            llm_role=u.LLMRole.PRIMARY,
            text=text,
            metadata={}
        )

    monkeypatch.setattr(p, 'initial_translation', lambda ctx: mk('FAST-TEXT'))

    seen = {}

    def fake_synopsis(ctx, text):
        seen['text'] = text
        return u.TranslationResult(
            stage=u.TranslationStage.SYNOPSIS,
            llm_role=u.LLMRole.PRIMARY,
            text='SYNOPSIS',
            metadata={}
        )

    monkeypatch.setattr(p, 'generate_synopsis', fake_synopsis)

    p.execute(
        source_lang='en', target_lang='ru', source_text='hello world',
        outline_text='', vocab_dict={}, vocab_entries=[],
        country='', style='text', fast_mode=True
    )

    assert seen.get('text') == 'FAST-TEXT'
