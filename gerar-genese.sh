#!/bin/bash
# Gênese do dono: a raiz de confiança da cadeia passa a ser a SUA chave. Rode no SEU Terminal (não pelo agente):
#   bash /Users/ulissesflores/Developer/eilikrineia/gerar-genese.sh
#
# 1. cria a sua chave com uma senha que só você sabe (o agente nunca vê a senha);
# 2. mostra a impressão digital da chave: guarde FORA deste Mac (foto, papel, outro aparelho). É ela que prova,
#    para sempre, que a gênese é sua e não uma cópia refeita por quem tem acesso ao Mac;
# 3. verifica a cadeia atual (feita só com chaves de agente), arquiva inteira em historico/ e assina a gênese,
#    que se compromete com o topo dela e com a lista de chaves válidas;
# 4. publica (verificador, carimbo no Bitcoin, varredura de segredos, push).
set -euo pipefail
REPO=/Users/ulissesflores/Developer/eilikrineia
PY=/opt/homebrew/bin/python3
CH="$REPO/privado/chaves/ulisses"
cd "$REPO"

if [ ! -f "$CH" ]; then
  echo "Crie uma senha que só você saiba. Ela será pedida de novo a cada assinatura sua."
  ssh-keygen -t ed25519 -C eilikrineia-ulisses -f "$CH"
fi
if ssh-keygen -y -P "" -f "$CH" >/dev/null 2>&1; then
  echo "A sua chave está SEM senha: qualquer programa no Mac poderia assinar por você."
  echo "Apague $CH e $CH.pub e rode de novo."
  exit 1
fi
echo
echo "Impressão digital da SUA chave. Guarde fora deste Mac:"
ssh-keygen -lf "$CH.pub"
echo
read -r -p "Guardou? Digite sim para assinar a gênese: " ok
[ "$ok" = "sim" ] || { echo "Nada assinado."; exit 1; }

"$PY" eilikrineia.py genese
"$PY" eilikrineia.py verificar --privado
"$PY" eilikrineia.py publicar
echo
echo "Gênese assinada e publicada. Próximo passo, se quiser o auditor separado:"
echo "  sudo bash $REPO/instalar-auditor-separado.sh"
