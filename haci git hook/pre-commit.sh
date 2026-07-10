#!/usr/bin/env bash
# haci-git pre-commit — closes the fence-swallow vector before it enters history.
# Refuses any commit whose staged .haci files have an unterminated fence.
# Install:  git config core.hooksPath .githooks   (per repo, one time)
set -euo pipefail
fail=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in *.haci)
    if ! python3 haci_git.py lint "$f"; then
      echo "  -> refusing commit: $f" >&2
      fail=1
    fi ;;
  esac
done < <(git diff --cached --name-only --diff-filter=ACM)
# self-check the toolchain too
python3 haci_git.py selftest >/dev/null || { echo "haci_git selftest failed"; fail=1; }
exit $fail
