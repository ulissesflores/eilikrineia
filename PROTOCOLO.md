# Protocolo eilikrineia

Regras para qualquer agente (Claude, Codex, Grok, Hermes ou outro) que escreva neste registro. O script recusa o que
viola as regras mecânicas; o auditor julga o resto.

## Papéis

| Papel | Quem | Pode registrar |
|---|---|---|
| `claude` | o agente que trabalha para o dono | fato-medido, afirmacao, opiniao, correcao, rodada |
| `auditor` | agente de OUTRO fornecedor | auditoria |
| `ulisses` | o dono, com chave própria protegida por senha | decisao, e qualquer outro tipo |

## Tipos

| Tipo | Quando | Evidência |
|---|---|---|
| `fato-medido` | o resultado de um comando, uma contagem, uma medição | obrigatória: a saída real, salva em arquivo |
| `afirmacao` | o que o agente diz ao dono que fez ou que funciona | obrigatória |
| `opiniao` | hipótese, recomendação, palpite | opcional; nunca vira fato sem nova entrada com evidência |
| `decisao` | o que o dono decidiu | assinada pela chave dele |
| `correcao` | o agente mudou de posição ou errou | aponta o hash da entrada corrigida; a antiga fica |
| `rodada` | uma execução de trabalho (entradas, saídas, provas) | obrigatória: os arquivos da execução |
| `auditoria` | veredito do auditor sobre uma entrada | obrigatória: a resposta bruta do auditor |
| `genese` | primeira entrada; só o dono; fixa a lista de chaves válidas e assume a cadeia anterior | lista de chaves, protocolo, código |
| `chaves` | o dono troca ou acrescenta uma chave; só o dono | a lista de chaves nova |

## Regras

1. Nada se edita nem se apaga. Mudar de ideia é uma `correcao`.
2. Toda frase do agente ao dono que diga "funciona", "provado", "feito", "medido" precisa de uma entrada com evidência,
   e a mensagem cita o número da entrada. Sem evidência, a frase é opinião e se diz como opinião.
3. Evidência é o arquivo real (saída de comando, log, resultado), nunca um resumo escrito pelo próprio agente.
4. O agente não escreve vereditos de auditoria nem assina pelo auditor.
5. O texto fica na pasta privada. Só se publica o hash, até o dono decidir revelar.
6. Omissão é falha: o auditor pode marcar afirmação de fato sem entrada.
7. Uma entrada, um fato. Interpretação ("isso quer dizer que...") vai numa entrada `opiniao` separada. Medido em
   23/10: misturar fato e interpretação na mesma entrada leva o auditor a "parcial" mesmo com o fato sustentado.
8. Evidência pequena e específica, extraída por comando, com o comando escrito no topo do arquivo. O auditor vê só o
   começo e o fim de arquivos grandes.
9. O que o agente disse antes só vira evidência com o trecho literal da conversa (transcript), nunca de memória.
10. A raiz de confiança é do dono: a cadeia começa pela gênese assinada pela chave dele (com senha), e a lista de
    chaves só muda com entrada `chaves` assinada por ele. Agente não tem como assinar nenhuma das duas.

## Comandos

```bash
python3 eilikrineia.py registrar --papel claude --tipo fato-medido --texto "..." --evidencia caminho/da/saida.txt
python3 eilikrineia.py registrar --papel claude --tipo correcao --texto "..." --evidencia ... --corrige <hash>
python3 eilikrineia.py verificar --privado
python3 eilikrineia.py auditar --auditor grok
python3 eilikrineia.py revelar <seq>
bash gerar-genese.sh                      # o dono, no Terminal dele: cria a chave com senha e assina a gênese
sudo bash instalar-auditor-separado.sh    # o dono: auditor em conta separada, com troca de chave assinada por ele
```
