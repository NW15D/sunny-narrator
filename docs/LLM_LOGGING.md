# LLM Call Logging

## Overview

This module logs all LLM API calls for debugging purposes. Each call is logged with:

- **Timestamp**: When the call was made
- **Stage**: Pipeline stage (INITIAL, REFLECTION, IMPROVE, FINAL, SYNOPSIS)
- **Role**: LLM role (PRIMARY, SECONDARY)
- **Model**: Model name used
- **Temperature**: Temperature setting
- **Max Tokens**: Maximum tokens requested
- **JSON Mode**: Whether JSON mode was enabled
- **Tokens Used**: Actual tokens consumed
- **Duration**: Request duration in milliseconds
- **Prompt Preview**: First 200 chars of user prompt
- **Response Preview**: First 200 chars of response
- **Full Prompts**: Complete system and user prompts (in JSON)
- **Full Response**: Complete LLM response (in JSON)

## Log File Location

```
sunny-narrator/logs/llm_calls.log
```

## Log Format

Each line is a JSON object:

```json
{
  "timestamp": "2026-03-31T12:00:00.000000",
  "stage": "INITIAL",
  "role": "PRIMARY",
  "model": "Mistral",
  "temperature": 0.01,
  "max_tokens": 8192,
  "json_mode": false,
  "tokens_used": 1234,
  "duration_ms": 1523.45,
  "prompt_preview": "Translate the following text...",
  "response_preview": "Переведённый текст...",
  "full_prompts": {
    "system": "You are a professional translator...",
    "user": "Translate: Hello world"
  },
  "full_response": "Переведённый текст..."
}
```

## Usage

Logging is automatic - no configuration needed. All LLM calls through `llm_service.complete()` are logged.

## Analyzing Logs

```bash
# View last 10 calls
tail -n 10 logs/llm_calls.log | jq .

# Find calls with high token usage
cat logs/llm_calls.log | jq 'select(.tokens_used > 1000)'

# Find slow calls (> 5 seconds)
cat logs/llm_calls.log | jq 'select(.duration_ms > 5000)'

# Count calls by stage
cat logs/llm_calls.log | jq -r '.stage' | sort | uniq -c

# Extract all prompts for a specific stage
cat logs/llm_calls.log | jq 'select(.stage == "INITIAL") | .full_prompts.user'
```

## Error Logging

Errors are logged with format:
```json
{
  "timestamp": "2026-03-31T12:00:00.000000",
  "stage": "INITIAL",
  "role": "PRIMARY",
  "model": "Mistral",
  "error": "Connection timeout",
  "prompt_preview": "..."
}
```

## Security Notes

- Logs contain full prompts and responses - may include sensitive content
- Log files are gitignored (*.log)
- Rotate logs periodically in production
