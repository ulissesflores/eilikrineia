#!/bin/bash
# Separa o auditor da eilikrineia numa conta própria do macOS. Rode UMA vez, como o dono, com:
#   sudo bash /Users/ulissesflores/Developer/eilikrineia/instalar-auditor-separado.sh
#
# Depois disto:
# - a chave privada do auditor só existe na conta "eilikrineia-auditor"; a antiga, que o agente conseguia ler, é
#   aposentada (vale só para entradas anteriores à troca) e apagada;
# - a chave de implantação do GitHub (escrita só neste repositório) só existe na conta do auditor;
# - o remoto passa a ser SSH: a sessão do agente, sem essa chave, não empurra mais;
# - um agendador do sistema roda de hora em hora, na conta do auditor: auditar (Grok) e publicar.
# Passo manual no fim: o login do Grok na conta do auditor (código de dispositivo).
set -euo pipefail

REPO=/Users/ulissesflores/Developer/eilikrineia
DONO=ulissesflores
AUD=eilikrineia-auditor
GRUPO=eilikrineia
PY=/opt/homebrew/bin/python3
GH=/opt/homebrew/bin/gh
CASA=/Users/$AUD
PLIST=/Library/LaunchDaemons/com.ulisses.eilikrineia.auditor.plist

[ "$(id -u)" = 0 ] || { echo "Rode com sudo."; exit 1; }
[ -f "$REPO/eilikrineia.py" ] || { echo "Repositório não encontrado em $REPO."; exit 1; }
grep -q '"tipo": "genese"' "$REPO/cadeia/000001.json" 2>/dev/null || { echo "Rode antes a gênese: bash $REPO/gerar-genese.sh"; exit 1; }
como_dono() { sudo -u "$DONO" -H "$@"; }
como_aud() { sudo -u "$AUD" -H "$@"; }

echo "1/8 grupo e conta do auditor"
dseditgroup -o read "$GRUPO" >/dev/null 2>&1 || dseditgroup -o create "$GRUPO"
if ! id "$AUD" >/dev/null 2>&1; then
  SENHA=$(openssl rand -base64 30)
  sysadminctl -addUser "$AUD" -fullName "eilikrineia auditor" -password "$SENHA" -home "$CASA" >/dev/null 2>&1
  createhomedir -c -u "$AUD" >/dev/null
  dscl . create "/Users/$AUD" IsHidden 1
  umask 077; printf '%s\n' "$SENHA" > /var/root/eilikrineia-auditor.senha
fi
dseditgroup -o edit -a "$DONO" -t user "$GRUPO"
dseditgroup -o edit -a "$AUD" -t user "$GRUPO"

echo "2/8 permissões compartilhadas (cadeia, carimbos, textos, acervo; NUNCA privado/chaves)"
como_dono git -C "$REPO" config core.sharedRepository group   # git passa a criar arquivos graváveis pelo grupo
chgrp "$GRUPO" "$REPO" "$REPO/privado"
chmod 750 "$REPO/privado"
for d in cadeia chaves tempo .git privado/textos privado/acervo privado/auditorias privado/evidencias; do
  [ -e "$REPO/$d" ] || continue
  chgrp -R "$GRUPO" "$REPO/$d"
  chmod -R g+rwX "$REPO/$d"
  find "$REPO/$d" -type d -exec chmod g+s {} +
done
chmod 700 "$REPO/privado/chaves"
como_aud test -r "$REPO/eilikrineia.py" || { echo "A conta do auditor não consegue ler $REPO."; exit 1; }

echo "3/8 chave nova do auditor, só na conta dele, e aposentadoria da antiga"
install -d -o "$AUD" -m 700 "$CASA/.eilikrineia"
[ -f "$CASA/.eilikrineia/auditor" ] || como_aud ssh-keygen -q -t ed25519 -N "" -C eilikrineia-auditor-separado -f "$CASA/.eilikrineia/auditor"
PUB=$(mktemp); cp "$CASA/.eilikrineia/auditor.pub" "$PUB"; chmod 644 "$PUB"
como_dono "$PY" "$REPO/eilikrineia.py" --raiz "$REPO" rotacionar auditor "$PUB"
rm -f "$PUB"
echo "   A troca de chave precisa da SUA assinatura (vai pedir a senha da sua chave):"
como_dono "$PY" "$REPO/eilikrineia.py" --raiz "$REPO" registrar --papel ulisses --tipo chaves \
  --texto "Troco a chave do auditor: a nova existe só na conta $AUD; a antiga, que o agente podia ler, vale só até agora." \
  --evidencia "$REPO/chaves/allowed_signers"
[ -f "$REPO/privado/chaves/auditor" ] && rm -P "$REPO/privado/chaves/auditor" "$REPO/privado/chaves/auditor.pub"

echo "4/8 chave de implantação do GitHub (escrita só em ulissesflores/eilikrineia)"
[ -f "$CASA/.eilikrineia/implantacao" ] || como_aud ssh-keygen -q -t ed25519 -N "" -C eilikrineia-implantacao -f "$CASA/.eilikrineia/implantacao"
PUB=$(mktemp); cp "$CASA/.eilikrineia/implantacao.pub" "$PUB"; chmod 644 "$PUB"
como_dono "$GH" repo deploy-key add "$PUB" --repo ulissesflores/eilikrineia --allow-write --title "auditor eilikrineia (conta separada)" || echo "   (chave de implantação já cadastrada?)"
rm -f "$PUB"

echo "5/8 git na conta do auditor e remoto por SSH"
install -d -o "$AUD" -m 700 "$CASA/.ssh"
ssh-keyscan -t ed25519 github.com 2>/dev/null | como_aud tee -a "$CASA/.ssh/known_hosts" >/dev/null
como_aud git config --global --add safe.directory "$REPO"
como_aud git config --global user.name "Ulisses Flores"
como_aud git config --global user.email "c.ulisses@gmail.com"
como_dono git -C "$REPO" remote set-url origin git@github.com:ulissesflores/eilikrineia.git

echo "6/8 Grok na conta do auditor"
install -d -o "$AUD" -m 755 "$CASA/.grok" "$CASA/.grok/bin"
cp -R "/Users/$DONO/.grok/bin/." "$CASA/.grok/bin/"
chown -R "$AUD" "$CASA/.grok"

echo "7/8 agendador de hora em hora (auditar + publicar), na conta do auditor"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.ulisses.eilikrineia.auditor</string>
  <key>UserName</key><string>$AUD</string>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key><dict>
    <key>EILIKRINEIA_CHAVE_AUDITOR</key><string>$CASA/.eilikrineia/auditor</string>
    <key>EILIKRINEIA_CHAVE_IMPLANTACAO</key><string>$CASA/.eilikrineia/implantacao</string>
    <key>HOME</key><string>$CASA</string>
    <key>PATH</key><string>$CASA/.grok/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-c</string>
    <string>$PY $REPO/eilikrineia.py auditar --auditor grok; $PY $REPO/eilikrineia.py publicar</string>
  </array>
  <key>StartInterval</key><integer>3600</integer>
  <key>StandardOutPath</key><string>$CASA/.eilikrineia/agendador.log</string>
  <key>StandardErrorPath</key><string>$CASA/.eilikrineia/agendador.log</string>
</dict></plist>
PL
chmod 644 "$PLIST"
launchctl bootout system "$PLIST" 2>/dev/null || true
launchctl bootstrap system "$PLIST"

echo "8/8 registro na cadeia"
como_dono "$PY" "$REPO/eilikrineia.py" --raiz "$REPO" registrar --papel claude --tipo fato-medido \
  --texto "Auditor separado instalado: chave nova só na conta $AUD; a chave antiga do auditor, que o agente podia ler, foi aposentada (valid-before) e apagada; vereditos anteriores a esta entrada foram assinados com ela." \
  --evidencia "$REPO/chaves/allowed_signers"

echo
echo "PRONTO. Falta UM passo seu, o login do Grok na conta do auditor:"
echo "  sudo -u $AUD -H $CASA/.grok/bin/grok login --device-code"
echo "Senha da conta do auditor (não precisa usar): /var/root/eilikrineia-auditor.senha"
