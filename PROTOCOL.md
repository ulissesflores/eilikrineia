# Protocol

Rules for any agent (Claude, Codex, Grok, Hermes or other) that writes to this ledger. The program refuses what
breaks the mechanical rules; the auditor judges the rest.

## Roles

| Role | Who | May record |
|---|---|---|
| `owner` | the person; key protected by a passphrase the agent never sees | `genesis`, `keys`, `code`, `decision`, and any other type |
| `agent` | the AI agent working for the owner | `measured`, `assertion`, `opinion`, `correction`, `run` |
| `auditor` | a model from another vendor, in a separate OS account | `audit`, `checkpoint` |

## Types

| Type | When | Evidence |
|---|---|---|
| `measured` | a count, a match, a value read from a file | required: typed claims decided by code |
| `assertion` | what the agent tells the owner it did or found | required; always read by the auditor model |
| `opinion` | hypothesis, recommendation | none; never judged as fact |
| `correction` | the agent was wrong or changed position | points to the corrected entry, which stays |
| `run` | a unit of work | inputs and outputs attached by hash |
| `checkpoint` | one per auditor run: "verified through #N" with every verdict of the run | the auditor's raw replies, attached by hash |
| `audit` | auditor alarm: an entry already witnessed changed or vanished | the alarm report |
| `genesis`, `keys`, `code`, `decision` | owner only | — |

## Evidence: never whole files

- **Claim**: `{"predicate", "args", "evidence": "FILE:FIRST-LAST"}` or `"FILE#/json/pointer"`.
- The program copies the file into the vault (gzip, named by the SHA-256 of the original bytes, read-only), cuts the
  excerpt and stores its hash.
  An excerpt longer than 2,000 characters is refused: narrow the locator.
- Predicates `number`, `contains`, `equals` are decided by code. Only `semantic` claims reach a model, and the model
  receives only the excerpts.
- Large files go as **attachments**: committed by hash, never sent to a model.

## Rules

1. Nothing is edited or deleted. Changing position is a `correction`.
2. Every sentence to the owner that says "works", "proven", "done", "measured" needs an entry with evidence, and the
   message cites the entry number. Without evidence it is an opinion and is said as one.
3. One entry, one fact. Interpretation goes in a separate `opinion`.
4. Evidence is the real output (log, command result, file), extracted by a command, never a summary written by the
   agent. What the agent said before becomes evidence only as a literal transcript excerpt.
5. The agent never writes audits or signs as the auditor.
6. The trust root is the owner: the chain starts with the owner's genesis; the key list and the auditor's code change
   only with an owner-signed `keys` or `code` entry.
7. Omission is a failure: an auditor may flag a factual statement to the owner that has no entry.

## Commands

```bash
python3 eilikrineia.py record --role agent --type measured --text "The suite ran 17 tests." --claims claims.json
python3 eilikrineia.py record --role agent --type assertion --text "..." --evidence log.txt:12-20
python3 eilikrineia.py record --role agent --type run --text "..." --attach big-output.json
python3 eilikrineia.py verify            # public: chain, signatures, owner-signed key list
python3 eilikrineia.py verify --private  # plus texts vs commitments and every excerpt vs the vault
python3 eilikrineia.py reveal 12         # text + salt of one entry, to publish when the owner decides
```

`claims.json`:

```json
[{"predicate": "number", "args": {"pattern": "Ran (\\d+) tests", "value": 17}, "evidence": "test-output.txt:1-4"}]
```
