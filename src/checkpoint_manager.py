"""Checkpoint manager for translation progress persistence.

Handles atomic save/load of translation checkpoints with corruption recovery.
Extracted from TranslationEngine in app.py.
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import Iterable

logger = logging.getLogger(__name__)

# Bumped from 1 when checkpoints gained a fingerprint. A version 1 file has no
# fingerprint to compare, so it can never be proven safe to resume from.
CHECKPOINT_VERSION = 2


def compute_fingerprint(chunks: Iterable[str], **params) -> str:
    """Digest of everything that decides how a book was sliced into chunks.

    Resuming a translation means "continue at chunk N of the same list". Until
    this existed, nothing checked the second half of that sentence: the only
    guard was that the checkpoint named the same book path. Any change to
    chunking, to the text cleanup that runs before it, or to max_chunk_size
    silently re-sliced the book, and the saved chunks were then spliced onto a
    different set of boundaries — duplicating some passages, dropping others,
    without a single error. Comparing this digest turns that into a clean
    restart instead.

    Args:
        chunks: The chunk texts, in order, exactly as they will be translated.
        **params: Anything else that changes the slicing or the translation
            target (max_chunk_size, source_lang, target_lang, ...). Order does
            not matter; keys are sorted before hashing.
    """
    h = hashlib.sha256()
    h.update(f"v{CHECKPOINT_VERSION}".encode('utf-8'))
    for key in sorted(params):
        h.update(f"\x00{key}={params[key]}".encode('utf-8'))
    count = 0
    for chunk in chunks:
        h.update(b"\x00")
        # surrogatepass: broken EPUBs yield lone surrogates, and a checkpoint
        # helper must never be the thing that raises on them.
        h.update(chunk.encode('utf-8', 'surrogatepass'))
        count += 1
    h.update(f"\x00n={count}".encode('utf-8'))
    return h.hexdigest()


class CheckpointManager:
    """Manages translation checkpoint save/load with corruption handling."""

    def __init__(self, checkpoint_path: str):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_path: Path to the checkpoint JSON file.
        """
        self.checkpoint_path = checkpoint_path

    def exists(self) -> bool:
        """Check if checkpoint file exists."""
        return os.path.exists(self.checkpoint_path)

    def remove(self) -> None:
        """Remove checkpoint file if it exists."""
        if os.path.exists(self.checkpoint_path):
            os.remove(self.checkpoint_path)
            logger.info(f"Checkpoint removed: {self.checkpoint_path}")

    def save(self, chunk_id: int, section_idx: int, chunk_idx: int,
             stats: dict, total_source_len: int, total_target_len: int,
             synopsis_history: dict, book_path: str, start_time_iso: str,
             extra: dict | None = None, fingerprint: str | None = None) -> None:
        """
        Save translation progress to checkpoint file (atomic write).

        Args:
            chunk_id: Last processed chunk global ID.
            section_idx: Last processed section index.
            chunk_idx: Last processed chunk index within section.
            stats: Statistics dict (successful, failed, total_tokens, etc).
            total_source_len: Total source characters processed.
            total_target_len: Total target characters produced.
            synopsis_history: Synopsis cache dict from SynopsisManager.
            book_path: Path to the book being translated.
            start_time_iso: ISO timestamp of translation start.
            fingerprint: Digest from compute_fingerprint() identifying the
                chunk list this progress refers to. Omitting it produces a
                checkpoint that load() can never validate, so pass it.
        """
        checkpoint = {
            "version": CHECKPOINT_VERSION,
            "book_path": book_path,
            "last_chunk": chunk_id,
            "last_section_idx": section_idx,
            "last_chunk_idx": chunk_idx,
            "stats": stats,
            "lengths": {
                "total_source_len": total_source_len,
                "total_target_len": total_target_len
            },
            "synopsis_history": synopsis_history,
            "created_at": start_time_iso,
            "updated_at": datetime.now().isoformat()
        }
        if fingerprint is not None:
            checkpoint["fingerprint"] = fingerprint
        if extra:
            checkpoint["extra"] = extra

        # Atomic write (temp + rename)
        temp_file = self.checkpoint_path + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, self.checkpoint_path)
            logger.debug(f"Checkpoint saved: {self.checkpoint_path}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def load(self, expected_fingerprint: str | None = None) -> dict | None:
        """
        Load checkpoint from file.

        Args:
            expected_fingerprint: Digest of the chunk list about to be
                translated (see compute_fingerprint). When given, a checkpoint
                whose fingerprint differs — or which predates fingerprinting
                entirely — is deleted and None is returned, so the caller
                starts fresh. Resuming such a checkpoint would splice progress
                onto a different set of chunk boundaries and quietly corrupt
                the output, which is far worse than re-translating.

        Returns:
            Checkpoint dict if valid, None if no file, corrupt, or stale.
            On corruption, saves a .corrupt backup and logs a warning.
        """
        if not os.path.exists(self.checkpoint_path):
            return None

        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            # Save corrupt backup
            corrupt_path = self.checkpoint_path + ".corrupt"
            try:
                os.replace(self.checkpoint_path, corrupt_path)
                logger.warning(f"Corrupt checkpoint saved as: {corrupt_path}")
            except OSError:
                logger.error(f"Could not save corrupt checkpoint backup")
            logger.warning(f"Checkpoint corrupted ({e}), starting fresh")
            return None

        if expected_fingerprint is not None:
            saved_fingerprint = checkpoint.get("fingerprint")
            if saved_fingerprint != expected_fingerprint:
                reason = (
                    "it predates checkpoint fingerprinting"
                    if not saved_fingerprint
                    else "the book no longer splits into the same chunks"
                )
                logger.warning(
                    f"Checkpoint {self.checkpoint_path} cannot be resumed "
                    f"({reason}); starting fresh."
                )
                self.remove()
                return None

        return checkpoint
