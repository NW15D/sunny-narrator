"""
Stage pipelining across chunks (PARALLEL_STAGES=2).

The translate and proofread LLMs sit on separate GPUs and each GPU serves one
request at a time. Done strictly in sequence, every chunk keeps one of them
idle:

    T: S1 initial, S5 synopsis      P: S2 reflection, S3 improve, S4 final edit

With the synopsis taken from the draft (S1 output) the translate side of chunk
n+1 no longer waits for the proofread side of chunk n:

    T: S1+S5 (n)  S1+S5 (n+1)  S1+S5 (n+2) ...
    P:            S2-S4 (n)    S2-S4 (n+1) ...

Chunks are still handled by the caller's own per-chunk code, one worker thread
per chunk (two workers, so at most two chunks are in flight). StageSequencer
only orders them, at three points of a chunk:

    draft      S1 and the draft synopsis are done: the next chunk may start
               (it needs this chunk's synopsis and dictionary candidates)
    translated the chunk left the LLM stages: the next chunk's proofread
               stages may start (one request per GPU, in book order)
    committed  the result was written out: the next chunk may be written

Everything a chunk needs from its predecessor (synopsis, glossary) is applied
in the on_draft callback; checkpoints must use the state captured there, not
the live one, which may already include the following chunk's draft.
"""

import threading
from contextlib import contextmanager
from typing import Callable, Optional

DRAFT, TRANSLATED, COMMITTED = 'draft', 'translated', 'committed'


class PipelineAborted(RuntimeError):
    """Another chunk failed: stop waiting for it."""


class StageSequencer:
    """Orders chunk indices at the draft / translated / committed points."""

    def __init__(self, first_index: int = 0):
        # Indices below first_index finished in an earlier run (resume)
        self.first_index = first_index
        self._cond = threading.Condition()
        self._done = {DRAFT: set(), TRANSLATED: set(), COMMITTED: set()}
        self._aborted = False

    def mark(self, kind: str, index: int):
        with self._cond:
            self._done[kind].add(index)
            self._cond.notify_all()

    def wait(self, kind: str, index: int):
        """Block until `kind` is reached for `index` (no-op before first_index)."""
        if index < self.first_index:
            return
        with self._cond:
            while index not in self._done[kind]:
                if self._aborted:
                    raise PipelineAborted(f"chunk {index} did not reach '{kind}'")
                self._cond.wait(timeout=1.0)

    def abort(self):
        with self._cond:
            self._aborted = True
            self._cond.notify_all()


class ChunkSlot:
    """One chunk's view of the sequencer, found by the pipeline via current_slot()."""

    def __init__(self, sequencer: StageSequencer, index: int,
                 on_draft: Optional[Callable[[str, str, list], None]] = None):
        self.sequencer = sequencer
        self.index = index
        self.on_draft = on_draft
        self.drafted = False

    def draft_ready(self, synopsis: str, draft_translation: str, candidates: list):
        """First draft of the chunk: hand its synopsis on and let the next chunk start."""
        if self.drafted:
            return
        self.drafted = True
        try:
            if self.on_draft is not None:
                self.on_draft(synopsis, draft_translation, candidates)
        finally:
            self.sequencer.mark(DRAFT, self.index)

    def enter_proofread(self):
        """Wait for the previous chunk to leave the GPUs (idempotent)."""
        self.sequencer.wait(TRANSLATED, self.index - 1)


_local = threading.local()


def current_slot() -> Optional[ChunkSlot]:
    return getattr(_local, 'slot', None)


@contextmanager
def chunk_slot(sequencer: StageSequencer, index: int, on_draft=None):
    """Wrap one chunk's LLM work. Waits for the previous chunk's draft first."""
    sequencer.wait(DRAFT, index - 1)
    slot = ChunkSlot(sequencer, index, on_draft)
    _local.slot = slot
    try:
        yield slot
    finally:
        _local.slot = None
        # A chunk that failed before its draft must not block the next one
        sequencer.mark(DRAFT, index)
        sequencer.mark(TRANSLATED, index)
