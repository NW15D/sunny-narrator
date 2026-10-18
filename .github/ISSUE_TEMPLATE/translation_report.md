---
name: Translation report
about: Tell how a translation went - good or bad (no programming needed)
title: 'Translation report: <source> -> <target>, <model>'
labels: translation-report
assignees: ''

---

* Book (title; a link if it is in the public domain):

* Source -> target language:

* Models (translate / proofread), quantization, local or hosted API:

* Mode: full (5 stages) / `FAST_TRANS=true`

* Input and output format (FB2, EPUB, DOCX, PDF, TXT):

* With a dictionary (`.dic`)? Built by the tool or by hand?

* What came out well:

* What went wrong (gender of a character, a name translated in two ways, words in two alphabets, a lost paragraph, style, ...), with a short passage of the source and of the translation:

* Time and hardware (GPU / VRAM), if you know:

Attach, if you can: the `.dic`, `<book>.dictcheck.txt`, the run report, `logs/llm_calls_YYYY-MM-DD.log` (`LLM_LOGGING=true`). No API keys, please.
