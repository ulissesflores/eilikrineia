#!/bin/bash
# The auditor's scheduled job. Installed by install-auditor-macos.sh into the auditor's account, owned by root,
# so neither the agent nor the auditor can change it.
#
# It runs a PINNED copy of eilikrineia.py, never the repository's file directly. The job never replaces the pinned
# copy: it changes only when the owner signs a 'code' entry and re-runs the installer with sudo, which checks the
# hash first. (Until 1.0.1 the job adopted owner-signed code by itself; an adversary on the same machine could
# turn that into running older or unchecked code, so adoption is no longer automatic.)
set -uo pipefail
: "${EILIKRINEIA_REPO:?set EILIKRINEIA_REPO}"
PIN="$HOME/.eilikrineia/eilikrineia.py"
PY="${EILIKRINEIA_PYTHON:-python3}"
date -u

# The witness runs first: if someone forged or cut the chain, that becomes a signed alarm before anything else.
"$PY" "$PIN" --root "$EILIKRINEIA_REPO" witness

cmp -s "$EILIKRINEIA_REPO/eilikrineia.py" "$PIN" \
  || echo "repository code differs from the pinned copy: not adopted (the owner re-runs the installer to change it)"
if ! "$PY" "$PIN" --root "$EILIKRINEIA_REPO" pinned-ok "$PIN" | grep -q '"ok": true'; then
  echo "REFUSING TO RUN: the pinned code is not the owner-signed hash"
  exit 1
fi

"$PY" "$PIN" --root "$EILIKRINEIA_REPO" audit --auditor "${EILIKRINEIA_AUDITOR:-grok}"
"$PY" "$PIN" --root "$EILIKRINEIA_REPO" publish
