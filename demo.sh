#!/bin/bash
# Collect the list of epub files
files=("books/eternal-moment.pg.epub" "books/forster-short-fiction.se.epub" )

mkdir -p ./logs

# Iterate over each file
for file in "${files[@]}"; do
  # basename strips the path, %.* strips the extension
  short=$(basename "$file" .epub)

  printf 'Translating: %s\n' "$file"

  # Run the main app in the foreground: the exit code stays available
  # (previously "& ... wait $app_pid" swallowed it, so process termination --
  # whether successful or an OOM-kill -- was indistinguishable from a hang).
  FILE="$file" ./.venv/bin/python app.py > "./logs/$short.log" 2>&1
  rc=$?

  # Do not break the loop on a single file's failure -- otherwise the first
  # book crashing (as already happened: the EPUB build hung/was killed with no
  # traceback) stops the whole batch and the remaining books never translate.
  if [ $rc -eq 0 ]; then
    printf 'OK: %s\n' "$file"
  else
    printf 'ERROR: %s (code %d, log ./logs/%s.log)\n' "$file" "$rc" "$short"
  fi
done

printf 'All books processed.\n'
