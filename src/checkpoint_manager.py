"""Checkpoint manager for translation progress persistence.

Handles atomic save/load of translation checkpoints with corruption recovery.
Extracted from TranslationEngine in app.py.
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


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
             synopsis_history: dict, book_path: str, start_time_iso: str) -> None:
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
        """
        checkpoint = {
            "version": 1,
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

    def load(self) -> dict | None:
        """
        Load checkpoint from file.

        Returns:
            Checkpoint dict if valid, None if no file or corrupt.
            On corruption, saves a .corrupt backup and logs a warning.
        """
        if not os.path.exists(self.checkpoint_path):
            return None

        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                return json.load(f)
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
