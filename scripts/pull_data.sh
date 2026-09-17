#!/bin/sh
# Fetch the collector's live document from the data branch into ./data, for local runs and previews.
# Collector output is never committed on main; this is how a checkout gets a `prev` to run against.
set -e
cd "$(dirname "$0")/.."
git fetch -q origin data
mkdir -p data/history
git show origin/data:latest.json > data/latest.json
for f in $(git ls-tree --name-only origin/data history/); do git show "origin/data:$f" > "data/$f"; done
echo "data/latest.json <- origin/data ($(git log -1 --format='%h %cd' --date=format:'%d %b %H:%M' origin/data))"
