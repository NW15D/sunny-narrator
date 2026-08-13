"""
LLM Logger Module - Logs all LLM calls with prompts and responses.

Logs to: logs/llm_calls_YYYY-MM-DD.log

Each log entry contains:
- timestamp: ISO format
- stage: TranslationStage name
- role: LLMRole (TRANSLATE/PROOFREAD)
- model: Model name
- temperature: Temperature used
- duration_ms: Execution time in milliseconds
- tokens_input: Input tokens
- tokens_output: Output tokens
- tokens_total: Total tokens
- prompt_system: System prompt (if any)
- prompt_user: User prompt
- response: LLM response
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class LLMCallLog:
    """Data class for a single LLM call log entry."""
    timestamp: str
    stage: str
    role: str
    model: str
    temperature: float
    duration_ms: int
    tokens_input: int
    tokens_output: int
    tokens_total: int
    prompt_system: str
    prompt_user: str
    response: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class LLMLogger:
    """
    Logger for LLM calls.
    
    Writes structured JSON logs to daily rotating files.
    Each log entry is a JSON line (JSONL format).
    """
    
    def __init__(self, log_dir: str = "logs", enabled: bool = True):
        """
        Initialize LLM logger.
        
        Args:
            log_dir: Directory for log files (default: logs/)
            enabled: Whether logging is enabled
        """
        self.enabled = enabled
        self.log_dir = Path(log_dir)
        self._current_file: Optional[Path] = None
        self._current_date: Optional[str] = None
        
        if enabled:
            self._ensure_log_dir()
    
    def _ensure_log_dir(self):
        """Create log directory if it doesn't exist."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_log_file(self) -> Path:
        """Get log file path for current date."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if today != self._current_date:
            self._current_date = today
            self._current_file = self.log_dir / f"llm_calls_{today}.log"
        
        return self._current_file
    
    def log_call(
        self,
        stage: str,
        role: str,
        model: str,
        temperature: float,
        duration_ms: int,
        tokens_input: int,
        tokens_output: int,
        tokens_total: int,
        prompt_system: str,
        prompt_user: str,
        response: str
    ):
        """
        Log a single LLM call.
        
        Args:
            stage: Translation stage name (INITIAL, REFLECTION, etc.)
            role: LLM role (TRANSLATE, PROOFREAD)
            model: Model name used
            temperature: Temperature setting
            duration_ms: Execution duration in milliseconds
            tokens_input: Number of input tokens
            tokens_output: Number of output tokens
            tokens_total: Total tokens used
            prompt_system: System prompt content
            prompt_user: User prompt content
            response: LLM response content
        """
        if not self.enabled:
            return
        
        log_entry = LLMCallLog(
            timestamp=datetime.now().isoformat(),
            stage=stage,
            role=role,
            model=model,
            temperature=temperature,
            duration_ms=duration_ms,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_total=tokens_total,
            prompt_system=prompt_system or "",
            prompt_user=prompt_user or "",
            response=response or ""
        )
        
        log_file = self._get_log_file()
        
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                json.dump(log_entry.to_dict(), f, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            # Don't let logging errors break the application
            logging.getLogger(__name__).error(f"Failed to write LLM log: {e}")
    
    def get_today_log_path(self) -> Optional[Path]:
        """Get path to today's log file."""
        if not self.enabled:
            return None
        return self._get_log_file()
    
    def get_recent_logs(self, days: int = 7) -> list:
        """
        Get list of recent log files.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of Path objects for log files
        """
        if not self.enabled or not self.log_dir.exists():
            return []
        
        log_files = []
        for file in self.log_dir.glob("llm_calls_*.log"):
            try:
                # Extract date from filename
                date_str = file.stem.replace("llm_calls_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                # Check if within requested range
                if (datetime.now() - file_date).days <= days:
                    log_files.append(file)
            except ValueError:
                continue
        
        return sorted(log_files, reverse=True)


# Global logger instance
_llm_logger: Optional[LLMLogger] = None


def init_llm_logger(log_dir: str = "logs", enabled: bool = True) -> LLMLogger:
    """
    Initialize global LLM logger.
    
    Args:
        log_dir: Directory for log files
        enabled: Whether logging is enabled
        
    Returns:
        LLMLogger instance
    """
    global _llm_logger
    _llm_logger = LLMLogger(log_dir=log_dir, enabled=enabled)
    return _llm_logger


def get_llm_logger() -> Optional[LLMLogger]:
    """Get global LLM logger instance."""
    return _llm_logger


def log_llm_call(**kwargs):
    """
    Convenience function to log an LLM call using global logger.
    
    Args:
        **kwargs: Arguments for LLMLogger.log_call()
    """
    if _llm_logger:
        _llm_logger.log_call(**kwargs)
