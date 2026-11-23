#!/usr/bin/env bash
# Launched by the Windows scheduled task NocturnoRove (EATP-037) through
# `conhost.exe --headless wsl.exe -e <this file>`. Runs the nightly runner from the repo
# root and appends everything to ~/.cache/rove-nightly/run.log. Extra args are passed on
# (e.g. --max 5 for a gentler night). The kill switch lives in Rove, not here.
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$HOME/.cache/rove-nightly"
cd "$(dirname "$0")/../.." || exit 1
echo "=== $(date '+%F %T') inicio" >> "$HOME/.cache/rove-nightly/run.log"
uv run python -m rove.nightly.runner "$@" >> "$HOME/.cache/rove-nightly/run.log" 2>&1
rc=$?
echo "=== $(date '+%F %T') fin (codigo $rc)" >> "$HOME/.cache/rove-nightly/run.log"
exit $rc
