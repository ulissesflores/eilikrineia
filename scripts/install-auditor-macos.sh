#!/bin/bash
# Put the auditor in a separate macOS account. Run once, as the owner, with sudo:
#   sudo bash scripts/install-auditor-macos.sh /path/to/eilikrineia <owner-macos-user> <github-owner>/<repo>
# Safe to run again: every step checks what already exists.
#
# After this:
# - the auditor's private key and the GitHub deploy key (write access to this repository only) live only in
#   the auditor's account;
# - the scheduler runs auditor-run.sh (owned by root) on every change to chain/ and hourly;
# - that job runs a pinned copy of eilikrineia.py that changes only when the owner re-runs this installer, and
#   only to an owner-signed hash;
# - pushes go over ssh:// with the deploy key, so a session in the owner's account cannot push.
set -euo pipefail
REPO=${1:?repository path}
OWNER=${2:?owner macOS user}
GH_REPO=${3:?github owner/repo}
AUD=eilikrineia-auditor
GROUP=eilikrineia
HOME_AUD=/Users/$AUD
STATE=$HOME_AUD/.eilikrineia
# sudo drops /opt/homebrew from PATH and macOS's own python3 is too old: pass EILIKRINEIA_PYTHON or use Homebrew's
PY=${EILIKRINEIA_PYTHON:-$( [ -x /opt/homebrew/bin/python3 ] && echo /opt/homebrew/bin/python3 || command -v python3 )}
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11+ required ($PY)."; exit 1; }
PLIST=/Library/LaunchDaemons/org.eilikrineia.auditor.plist
LOG="$REPO/private/audits/scheduler.log"

[ "$(id -u)" = 0 ] || { echo "Run with sudo."; exit 1; }
as_owner() { sudo -u "$OWNER" -H "$@"; }
as_aud() { sudo -u "$AUD" -H "$@"; }
verify_out() { as_owner "$PY" "$REPO/eilikrineia.py" --root "$REPO" verify || true; }
grep -q '"trust_root": "owner genesis"' <<<"$(verify_out)" || { echo "Sign the owner genesis first."; exit 1; }

echo "1/7 auditor account and group"
dseditgroup -o read "$GROUP" >/dev/null 2>&1 || dseditgroup -o create "$GROUP"
if ! id "$AUD" >/dev/null 2>&1; then
  sysadminctl -addUser "$AUD" -fullName "eilikrineia auditor" -password "$(openssl rand -base64 30)" -home "$HOME_AUD" >/dev/null 2>&1
  createhomedir -c -u "$AUD" >/dev/null
  dscl . create "/Users/$AUD" IsHidden 1
fi
dseditgroup -o edit -a "$OWNER" -t user "$GROUP" 2>/dev/null || true
dseditgroup -o edit -a "$AUD" -t user "$GROUP" 2>/dev/null || true

echo "2/7 shared folders (never private/keys)"
as_owner git -C "$REPO" config core.sharedRepository group
mkdir -p "$REPO/private/audits" "$REPO/stamps"
chown "$OWNER" "$REPO/private/audits" "$REPO/stamps"
chgrp "$GROUP" "$REPO" "$REPO/private"
chmod 750 "$REPO/private"
for d in chain keys stamps history .git private/texts private/vault private/audits; do
  [ -e "$REPO/$d" ] || continue
  chgrp -R "$GROUP" "$REPO/$d"
  chmod -R g+rwX "$REPO/$d"
  find "$REPO/$d" -type d -exec chmod g+s {} +
done
chmod 700 "$REPO/private/keys"
as_aud test -r "$REPO/eilikrineia.py" || { echo "The auditor account cannot read $REPO."; exit 1; }

echo "3/7 auditor key (only in the auditor's account)"
install -d -o "$AUD" -m 700 "$STATE"
[ -f "$STATE/auditor" ] || as_aud ssh-keygen -q -t ed25519 -N "" -C eilikrineia-auditor -f "$STATE/auditor"
if ! grep -q "$(awk '{print $2}' "$STATE/auditor.pub")" "$REPO/keys/allowed_signers"; then
  TMP="$REPO/private/.new-auditor.pub"; cp "$STATE/auditor.pub" "$TMP"; chown "$OWNER" "$TMP"
  as_owner "$PY" "$REPO/eilikrineia.py" --root "$REPO" rotate auditor "$TMP"
  rm -f "$TMP"
fi
if grep -q "differs from the list last signed" <<<"$(verify_out)"; then
  echo "   The key change needs YOUR signature (asks for your key's passphrase):"
  as_owner "$PY" "$REPO/eilikrineia.py" --root "$REPO" record --role owner --type keys \
    --text "Auditor key: lives only in the $AUD account."
fi

echo "4/7 deploy key (write access to $GH_REPO only)"
[ -f "$STATE/deploy" ] || as_aud ssh-keygen -q -t ed25519 -N "" -C eilikrineia-deploy -f "$STATE/deploy"
TMP="$REPO/private/.deploy.pub"; cp "$STATE/deploy.pub" "$TMP"; chown "$OWNER" "$TMP"
as_owner gh repo deploy-key add "$TMP" --repo "$GH_REPO" --allow-write --title "eilikrineia auditor" 2>/dev/null \
  || echo "   (deploy key already registered)"
rm -f "$TMP"

echo "5/7 git for the auditor; push only over ssh:// with the deploy key"
install -d -o "$AUD" -m 700 "$HOME_AUD/.ssh"
grep -q github.com "$HOME_AUD/.ssh/known_hosts" 2>/dev/null \
  || ssh-keyscan -t ed25519 github.com 2>/dev/null | as_aud tee -a "$HOME_AUD/.ssh/known_hosts" >/dev/null
as_aud git config --global --replace-all safe.directory "$REPO"
as_aud git config --global user.name "$(as_owner git -C "$REPO" config user.name)"
as_aud git config --global user.email "$(as_owner git -C "$REPO" config user.email)"
as_owner git -C "$REPO" config remote.origin.pushurl "ssh://git@github.com/$GH_REPO.git"

echo "6/7 the auditor model's CLI (grok) in the auditor's account"
install -d -o "$AUD" -m 755 "$HOME_AUD/.grok" "$HOME_AUD/.grok/bin"
if [ ! -x "$HOME_AUD/.grok/bin/grok" ] && [ -e "/Users/$OWNER/.grok/bin/grok" ]; then
  cp -L "/Users/$OWNER/.grok/bin/grok" "$HOME_AUD/.grok/bin/grok"   # -L: the owner's grok is a symlink
  chmod 755 "$HOME_AUD/.grok/bin/grok"
fi
chown -R "$AUD" "$HOME_AUD/.grok"

echo "7/7 pinned code, root-owned job, scheduler on every change to chain/"
if ! as_owner "$PY" "$REPO/eilikrineia.py" --root "$REPO" pinned-ok "$REPO/eilikrineia.py" | grep -q '"ok": true'; then
  echo "The repository's eilikrineia.py is not the owner-signed code; refusing to pin it."; exit 1
fi
install -o "$AUD" -m 644 "$REPO/eilikrineia.py" "$STATE/eilikrineia.py"
install -o root -g wheel -m 755 "$REPO/scripts/auditor-run.sh" "$STATE/run.sh"
touch "$LOG"; chown "$AUD:$GROUP" "$LOG"; chmod 664 "$LOG"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>org.eilikrineia.auditor</string>
  <key>UserName</key><string>$AUD</string>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key><dict>
    <key>EILIKRINEIA_REPO</key><string>$REPO</string>
    <key>EILIKRINEIA_PYTHON</key><string>$PY</string>
    <key>EILIKRINEIA_KEY_AUDITOR</key><string>$STATE/auditor</string>
    <key>EILIKRINEIA_KEY_DEPLOY</key><string>$STATE/deploy</string>
    <key>EILIKRINEIA_WITNESS</key><string>$STATE/witness.json</string>
    <key>HOME</key><string>$HOME_AUD</string>
    <key>PATH</key><string>$HOME_AUD/.grok/bin:$(dirname "$PY"):/usr/bin:/bin</string>
  </dict>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$STATE/run.sh</string></array>
  <key>WatchPaths</key><array><string>$REPO/chain</string></array>
  <key>StartInterval</key><integer>3600</integer>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL
chmod 644 "$PLIST"
launchctl bootout system "$PLIST" 2>/dev/null || true
launchctl bootstrap system "$PLIST"
launchctl kickstart -k system/org.eilikrineia.auditor || true

echo
echo "Done. If the auditor model is not signed in yet:"
echo "  sudo -u $AUD -H $HOME_AUD/.grok/bin/grok login --device-code"
