# Sampling — Temperatures, presence_penalty, Thinking

Every request carries the temperature of its stage, a `presence_penalty`
and the thinking switch. All three are sent explicitly, so the server's own
defaults (a llama.cpp model preset, a hosted provider) never decide them.

## Temperature by stage

| Stage | LLM | Variable | Default | Reference setup (`env.sample`) |
|---|---|---|---|---|
| INITIAL — translation | translate | `TEMP_INITIAL` | `TEMP_TRANSLATE` (0.01) | 0.05 |
| REFLECTION — finding errors | proofread | `TEMP_REFLECTION` | 0.4 | 0.2 |
| IMPROVE — applying the fixes | proofread | `TEMP_IMPROVE` | 0.4 | 0.2 |
| FINAL_EDIT — editing | proofread | `TEMP_FINAL_EDIT` | 0.15 | 0.1 |
| GENDER — fixing gender agreement | proofread (`GENDER_LLM`) | `TEMP_GENDER` | 0.05 | 0.05 |
| SYNOPSIS — context for the next chunk | translate | `TEMP_SYNOPSIS` | 0.15 | 0.15 |

`TEMP_TRANSLATE` and `TEMP_PROOFREAD` (default 0.7) are fallbacks: every stage
of the pipeline has its own variable, and only the requests outside the
stages — the dictionary translation (`--build-dict`, `dict extend`) and the
metadata — use the base temperature of their LLM.

The defaults are general-purpose; `env.sample` carries the lower values the
reference setup (Gemma 4 translates, Qwen 3.6 proofreads) runs with. Measure a
change with `app.py eval` (below) rather than by reading one chunk.

## presence_penalty

| Variable | Default | Stages |
|---|---|---|
| `PRESENCE_PENALTY_TRANSLATE` | 0 | INITIAL, SYNOPSIS |
| `PRESENCE_PENALTY_PROOFREAD` | 0 | IMPROVE, FINAL_EDIT, GENDER |
| `PRESENCE_PENALTY_REFLECTION` | 1.5 | REFLECTION |

Why it is sent at all: llama.cpp serves the Qwen preset with
`presence_penalty 1.5` unless a request says otherwise. A stage that writes the
text again is then penalized for the tokens of a word it has just written, and
writes the word with a Latin letter (`сприна` → `спринa`). REFLECTION is the
opposite: it writes a list, and without the penalty the list repeats until
`max_tokens` (2 truncations in 24 chunks at 0, none at 1.5).

## Thinking

`NOTHINK_TRANSLATE` and `NOTHINK_PROOFREAD` (default `true`) turn the models'
thinking off: every request carries `chat_template_kwargs.enable_thinking=false`
(llama.cpp, Gemma 4, Qwen 3) and `reasoning.effort="none"` (OpenRouter,
ProxyAPI — Qwen 3.6 thinks there unless told not to). Each server ignores the
other's field. The stages expect the answer itself; thinking costs tokens and
time, and REFLECTION's token budget assumes it is off.

## Seeing what is sent

With `LLM_LOGGING=true` every call is logged with its stage, model,
temperature, tokens and time (`logs/llm_calls_YYYY-MM-DD.log`, see
[LOGGING.md](LOGGING.md)); with `DEBUG=1` the console shows
`LLM Request [<role>]: <model>, <chars> chars, temp=…` for every request.

To compare settings on the same passages of a book with your models:

```bash
python app.py eval books/MyBook.epub --dic books/MyBook_ru.dic --count 8 --out logs/eval/a.json
TEMP_IMPROVE=0.4 python app.py eval books/MyBook.epub --dic books/MyBook_ru.dic --count 8 \
  --out logs/eval/b.json --compare logs/eval/a.json
```
