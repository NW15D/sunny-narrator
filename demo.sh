#!/bin/bash
# Collect the list of epub files
files=("books/eternal-moment.pg.epub" "books/forster-short-fiction.se.epub" )

# Target languages in order: "TARGET_LANG:COUNTRY". The dictionary for each is
# books/<book>_<TARGET_LANG>.dic - the name a run looks it up by anyway.
langs=(
  "ru:Россия"
  "es:España"
  "fr:France"
  "pl:Polska"
  "pt:Portugal"
  "tr:Türkiye"
  "zh:中国"
)

mkdir -p ./logs

# Iterate over each file, then over each target language
for file in "${files[@]}"; do
  # basename strips the path, %.* strips the extension
  short=$(basename "$file" .epub)

  for entry in "${langs[@]}"; do
    lang="${entry%%:*}"
    country="${entry#*:}"
    dict="${file%.epub}_${lang}.dic"

    if [ ! -f "$dict" ]; then
      printf 'SKIP: %s [%s] (no dictionary %s)\n' "$file" "$lang" "$dict"
      continue
    fi

    printf 'Translating: %s -> %s (%s), dictionary %s\n' "$file" "$lang" "$country" "$dict"

    # Run the main app in the foreground: the exit code stays available
    # (previously "& ... wait $app_pid" swallowed it, so process termination --
    # whether successful or an OOM-kill -- was indistinguishable from a hang).
    FILE="$file" TARGET_LANG="$lang" COUNTRY="$country" DICTIONARY="$dict" \
      ./.venv/bin/python app.py > "./logs/${short}_${lang}.log" 2>&1
    rc=$?

    # Do not break the loop on a single run's failure -- otherwise the first
    # crash (as already happened: the EPUB build hung/was killed with no
    # traceback) stops the whole batch and the remaining runs never translate.
    if [ $rc -eq 0 ]; then
      printf 'OK: %s [%s]\n' "$file" "$lang"
    else
      printf 'ERROR: %s [%s] (code %d, log ./logs/%s_%s.log)\n' "$file" "$lang" "$rc" "$short" "$lang"
    fi
  done
done

printf 'All books processed.\n'
