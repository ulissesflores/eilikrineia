#!/bin/bash
# The auditor's scheduled job. Installed by install-auditor-macos.sh into the auditor's account, owned by root,
# so neither the agent nor the auditor can change it.
#
# It runs a PINNED copy of eilikrineia.py, never the repository's file directly. The pinned copy is replaced
# only by a file whose SHA-256 the owner signed (genesis or a later 'code' entry). An agent that edits the
# repository's eilikrineia.py changes nothing the auditor does until the owner signs it.
set -uo pipefail
: "${EILIKRINEIA_REPO:?set EILIKRINEIA_REPO}"
PIN="$HOME/.eilikrineia/eilikrineia.py"
PY="${EILIKRINEIA_PYTHON:-python3}"
date -u

# The witness runs first, with the code already pinned: if someone forged or cut the chain, that becomes a signed
# alarm before anything else, and pinned-ok below then refuses to adopt code from the altered chain.
"$PY" "$PIN" --root "$EILIKRINEIA_REPO" witness

if ! cmp -s "$EILIKRINEIA_REPO/eilikrineia.py" "$PIN"; then
  if "$PY" "$PIN" --root "$EILIKRINEIA_REPO" pinned-ok "$EILIKRINEIA_REPO/eilikrineia.py" | grep -q '"ok": true'; then
    cp "$EILIKRINEIA_REPO/eilikrineia.py" "$PIN"
    echo "adopted new code: its hash is signed by the owner"
  else
    echo "repository code differs from the pinned copy and is NOT owner-signed: ignored"
  fi
fi
if ! "$PY" "$PIN" --root "$EILIKRINEIA_REPO" pinned-ok "$PIN" | grep -q '"ok": true'; then
  echo "REFUSING TO RUN: the pinned code is not the owner-signed hash"
  exit 1
fi

"$PY" "$PIN" --root "$EILIKRINEIA_REPO" audit --auditor "${EILIKRINEIA_AUDITOR:-grok}"
"$PY" "$PIN" --root "$EILIKRINEIA_REPO" publish
