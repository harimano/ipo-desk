#!/bin/sh
# Grep the built site for personal names, case-insensitive, whole site (HTML, JS, JSON, manifest).
#   scripts/names_grep.sh "Name One" "Name Two"     # exit 1 if any appears in _site/
# Names are arguments, never stored in the repo.
cd "$(dirname "$0")/.." || exit 2
rc=0
for n in "$@"; do
  c=$(grep -rIli -- "$n" _site | wc -l | tr -d ' ')
  echo "$n: $c file(s)"; [ "$c" = 0 ] || { rc=1; grep -rIli -- "$n" _site | head -5; }
done
exit $rc
