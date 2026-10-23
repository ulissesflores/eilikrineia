# εἰλικρίνεια · eilikrineia

> *Julgado à luz do sol.*

Um registro público de compromissos entre uma pessoa e os agentes de IA que trabalham para ela. Cada afirmação
feita por um agente é comprometida por hash, encadeada à anterior, assinada, auditada por um agente de outro
fornecedor e carimbada no tempo pelo Bitcoin. O conteúdo não precisa ser publicado para ser cobrado. O que se publica
é a impossibilidade de mudar o que foi dito sem que se veja.

---

## A palavra

**εἰλικρίνεια** (*eilikríneia*) é a palavra grega para pureza de intenção, sinceridade, aquilo que não tem mistura.
O adjetivo é **εἰλικρινής** (*eilikrinḗs*): puro, sem liga.

A explicação tradicional dos léxicos junta duas partes: **εἵλη** (*heílē*), o raio do sol, e **κρίνω** (*krínō*),
julgar, separar, discernir. Eilikrinḗs seria o que foi **examinado contra a luz do sol e achado sem defeito**.

Os próprios léxicos chamam essa origem de provável, não de certa. Richard Trench, nos *Sinônimos do Novo Testamento*,
lê a palavra menos como "transparente" e mais como **purgado, peneirado, sem mistura**. Outra conjectura antiga a liga
a algo limpo por ser rolado de um lado a outro. A origem é incerta.

Este projeto guarda as duas imagens e a incerteza junto delas:

- **A luz do sol:** expor ao público aquilo que se afirma, para que qualquer um examine.
- **A peneira:** separar o que é sustentado do que não é, sem misturar fato com opinião.

### A lenda que não usamos

Existe uma história famosa sobre a palavra latina *sincerus*: os oleiros romanos tapariam rachaduras com cera, e o
vaso honesto seria *sine cera*, "sem cera". É uma história bonita e é falsa. Dicionários como o Oxford e o
Merriam-Webster a rejeitam, e a origem mais aceita de *sincerus* é "de um só crescimento", não misturado.

Contamos isso de propósito. Um registro de sinceridade que abrisse com uma etimologia falsa porque ela soa melhor
seria a primeira violação do próprio protocolo. Aqui, nem a nossa história sobre o nome passa sem marcar o que é
certo e o que é provável.

## Por que funciona

Platão, no *Fédon* (65e–66a), descreve quem busca a verdade usando "o pensamento puro, ele mesmo por si mesmo"
(*αὐτῇ καθ᾽ αὑτὴν εἰλικρινεῖ τῇ διανοίᾳ*): sem deixar que nada de fora se misture ao exame. Paulo usa *eilikríneia*
para falar de uma conduta que pode ser mostrada e examinada (2 Coríntios 1:12; 2:17).

As duas ideias, a luz que expõe e o exame sem mistura, viram mecanismo:

| Ideia | Mecanismo |
|---|---|
| Ser examinado à luz do sol | Repositório público e carimbo no Bitcoin: qualquer pessoa verifica, sem pedir licença |
| Não ter mistura | Hash: mudar uma vírgula muda o hash inteiro; não há como alterar "um pouco" |
| Não trocar o que foi dito | Cadeia: cada entrada carrega o hash da anterior; reescrever uma quebra todas as seguintes |
| Mudar de ideia sem esconder | Correção é nova entrada que aponta a antiga; a antiga continua lá |
| Quem julga não é quem afirma | Auditor de outro fornecedor, em outra conta, assina o veredito |
| Pureza sem exposição | Compromisso com sal: publica-se o hash, o texto fica guardado até ser revelado |

## O que este repositório prova e o que não prova

**Prova:**
- que cada entrada existia, exatamente assim, até a data do carimbo no Bitcoin;
- que nenhuma entrada foi alterada ou removida depois;
- qual chave assinou cada entrada e cada veredito;
- que toda mudança de posição ficou registrada como correção.

**Não prova:**
- que uma afirmação é verdadeira. Prova que ela é rastreável, contestável e cara de sustentar se for falsa;
- qual modelo pensou. Prova qual chave assinou;
- o que nunca foi registrado. Omissão é o ponto mais fraco, e o auditor procura por ela.

## Verifique sem confiar em ninguém

```bash
git clone https://github.com/<conta>/eilikrineia
cd eilikrineia
python3 eilikrineia.py verificar
```

Só precisa de Python 3 e do `ssh-keygen` (OpenSSH 8.1 ou mais novo). O verificador confere a sequência, o encadeamento,
o hash de cada entrada, a assinatura de cada uma contra as chaves públicas em `chaves/allowed_signers` e as regras do
protocolo. A prova de tempo no Bitcoin (pasta `tempo/`) entra quando o carimbo for ligado.

Quem tem a pasta privada confere também que cada texto bate com o compromisso público e que nenhuma evidência mudou
depois do registro:

```bash
python3 eilikrineia.py verificar --privado
```

## Estrutura

```text
eilikrineia.py   registrar, verificar, auditar, revelar (biblioteca padrão + ssh-keygen)
PROTOCOLO.md     as regras que qualquer agente segue para escrever aqui
chaves/          chaves públicas dos papéis: pessoa, agente, auditor
cadeia/          uma entrada por arquivo, só hashes e assinaturas
tempo/           provas OpenTimestamps do topo da cadeia (quando ligado)
tests/           testes, incluindo os de adulteração
privado/         NUNCA publicado: textos, sais, caminhos de evidência, chaves privadas, respostas do auditor
```

## Fontes

- Léxicos gregos sobre εἰλικρίνεια e εἰλικρινής: [Bible Hub 1505](https://biblehub.com/greek/1505.htm),
  [Bible Hub 1506](https://biblehub.com/greek/1506.htm), [Blue Letter Bible G1506](https://www.blueletterbible.org/lexicon/G1506/tr).
- Trench, *Sinônimos do Novo Testamento*, verbete sobre εἰλικρινής: [texto](https://modernliteralversion.org/bibles/bs2/G5625up/Trench-85.htm).
- A lenda *sine cera* e a origem de *sincerus*: [Etymonline](https://www.etymonline.com/word/sincere),
  [Grammarphobia](https://grammarphobia.com/blog/2012/03/sincere.html), [Wikipedia](https://en.wikipedia.org/wiki/Sincerity).
- Platão, *Fédon*, texto grego e tradução de Fowler: [Ellopos](https://www.ellopos.net/elpenor/greek-texts/ancient-greece/plato-death.asp?pg=13),
  [Perseus](https://cts.perseids.org/read/greekLit/tlg0059/tlg004/perseus-eng2/65-66).
- OpenTimestamps: [opentimestamps.org](https://opentimestamps.org/), [anúncio de Peter Todd](https://petertodd.org/2016/opentimestamps-announcement).

## A raiz de confiança é do dono

Uma cadeia assinada só por chaves de agente pode ser refeita do zero por quem tem acesso às chaves. Por isso a cadeia
começa pela **gênese do dono**: a primeira entrada é assinada pela chave da pessoa, protegida por uma senha que o
agente nunca vê, e se compromete com a lista de chaves válidas. Qualquer mudança nessa lista (entrada `chaves`) também
exige a assinatura dela; o verificador reprova uma lista diferente da última assinada.

Duas coisas tornam a gênese impossível de falsificar depois:

- a **impressão digital da chave do dono**, guardada por ele fora da máquina;
- o **carimbo no Bitcoin** e o **arquivamento no Software Heritage** logo após a gênese: uma gênese refeita depois
  teria data posterior.

A cadeia anterior à gênese, feita só com chaves de agente, fica inteira em `historico/v0/` e a gênese se compromete
com o topo dela (campo `antecessora`). O verificador diz qual é a raiz de confiança de cada cadeia.

## Estado

- Cadeia, verificador e auditor funcionando desde 2026-10-23. O auditor é um modelo de outro fornecedor, chamado pela
  assinatura do próprio fornecedor, e assina os vereditos com a chave dele.
- Cada publicação carimba o topo da cadeia no OpenTimestamps (pasta `tempo/`). Um carimbo novo fica pendente até ser
  incluído num bloco do Bitcoin, o que leva algumas horas; a publicação seguinte completa os pendentes. Para conferir
  um carimbo completo: `ots verify tempo/<seq>.txt.ots` (precisa de um nó de Bitcoin seu) ou o verificador em
  https://opentimestamps.org.
- Evidências ficam num acervo privado, endereçado pelo próprio hash: o arquivo original pode mudar, a prova não.
- Erros ficam na cadeia. As primeiras entradas incluem correções do próprio agente, várias julgadas "parcial" pelo
  auditor, e quatro evidências perdidas porque o agente alterou depois um arquivo que tinha citado. O verificador as
  lista como "reconhecidas".

## Limites conhecidos

- O auditor ainda roda na mesma conta do sistema que o agente. A separação em outra conta está pronta em
  `instalar-auditor-separado.sh` e depende da senha de administrador do dono.
- Omissão: a cadeia impede alterar o que foi registrado, mas não obriga a registrar.
- A etimologia acima ainda será conferida em Beekes (*Etymological Dictionary of Greek*) e Chantraine (*DELG*), e o
  número exato de Stephanus da passagem do *Fédon*.
