"""
LLM Call Logger - Logs all LLM requests/responses with metadata.
"""
import logging
import json
import time
from datetime import datetime
from pathlib import Path

# Setup dedicated logger for LLM calls
llm_logger = logging.getLogger('llm_calls')
llm_logger.setLevel(logging.INFO)

# Create logs directory
log_dir = Path(__file__).resolve().parent.parent / 'logs'
log_dir.mkdir(exist_ok=True)

# File handler for LLM calls
log_file = log_dir / 'llm_calls.log'
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.INFO)

# Format: timestamp | stage | role | model | temp | tokens | duration | prompt_preview | response_preview
formatter = logging.Formatter('%(message)s')
file_handler.setFormatter(formatter)

llm_logger.addHandler(file_handler)


def log_llm_call(
    stage: str,
    role: str,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str,
    user_prompt: str,
    response_text: str,
    tokens_used: int,
    duration_ms: float,
    json_mode: bool = False
):
    """
    Log LLM call with all metadata.
    
    Args:
        stage: Pipeline stage (INITIAL, REFLECTION, IMPROVE, FINAL, SYNOPSIS)
        role: LLM role (PRIMARY, SECONDARY)
        model: Model name
        temperature: Temperature used
        max_tokens: Max tokens requested
        system_prompt: System prompt (may be empty)
        user_prompt: User prompt
        response_text: LLM response
        tokens_used: Tokens consumed
        duration_ms: Request duration in milliseconds
        json_mode: Whether JSON mode was enabled
    """
    # Truncate prompts for log (first 200 chars)
    prompt_preview = (user_prompt[:200] + '...') if len(user_prompt) > 200 else user_prompt
    response_preview = (response_text[:200] + '...') if len(response_text) > 200 else response_text
    
    # Replace newlines for single-line log
    prompt_preview = prompt_preview.replace('\n', ' ').replace('\r', ' ')
    response_preview = response_preview.replace('\n', ' ').replace('\r', ' ')
    
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'stage': stage,
        'role': role,
        'model': model,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'json_mode': json_mode,
        'tokens_used': tokens_used,
        'duration_ms': round(duration_ms, 2),
        'prompt_preview': prompt_preview,
        'response_preview': response_preview,
        'full_prompts': {
            'system': system_prompt if system_prompt else None,
            'user': user_prompt
        },
        'full_response': response_text
    }
    
    # Write as JSON line
    llm_logger.info(json.dumps(log_entry, ensure_ascii=False))


def log_llm_error(
    stage: str,
    role: str,
    model: str,
    error: str,
    user_prompt_preview: str
):
    """Log LLM error."""
    preview = (user_prompt_preview[:100] + '...') if len(user_prompt_preview) > 100 else user_prompt_preview
    preview = preview.replace('\n', ' ').replace('\r', ' ')
    
    error_entry = {
        'timestamp': datetime.now().isoformat(),
        'stage': stage,
        'role': role,
        'model': model,
        'error': error,
        'prompt_preview': preview
    }
    
    llm_logger.info(f"ERROR: {json.dumps(error_entry, ensure_ascii=False)}")
