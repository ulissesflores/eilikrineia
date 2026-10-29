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

---

## Wire format and verification (protocol 1, normative)

This section describes protocol 1 exactly as `eilikrineia.py` 1.0.0 implements it. Until now it lived only in code.
The key words MUST, MUST NOT, SHOULD and MAY are to be read as described in BCP 14 (RFC 2119, RFC 8174) when, and
only when, they appear in all capitals. The protocol version is independent of the program's SemVer version.

### Layout

| Path | Public | Content |
|---|---|---|
| `chain/NNNNNN.json` | yes | one entry per file, `NNNNNN` = `seq` zero-padded to 6 digits |
| `keys/allowed_signers` | yes | role keys in the ssh-keygen ALLOWED SIGNERS format, namespace `eilikrineia` |
| `stamps/NNNNNN.txt`, `.ots` | yes | `eilikrineia\nseq N\nhead H\n` and its OpenTimestamps proof |
| `private/texts/NNNNNN.json` | no | `{seq, hash, salt, text, claims, attachments}` |
| `private/vault/` | no | gzip copies of evidence, named by the SHA-256 of the original bytes |

### Canonical JSON

`canonical(x)` is UTF-8 JSON with keys sorted, no insignificant whitespace and no escaping of non-ASCII characters
(Python `json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`). On the domain used by
protocol 1 (integers below 2^53, strings, lists, objects with ASCII keys, no floating-point numbers) this output is
identical to RFC 8785 (JCS); it differs from JCS only for floating-point numbers and for keys outside the Basic
Multilingual Plane. This repository's own ledger stays inside the domain (ledger entry #71). Writers MUST NOT put
floating-point numbers or non-ASCII keys in any hashed or committed object; 1.0.0 does not enforce this yet (an
`equals` claim accepts any JSON value).

### Entry

| Field | Type | Hashed | Meaning |
|---|---|---|---|
| `seq` | integer | yes | 1, 2, 3, ... without gaps |
| `time` | string | yes | UTC, `YYYY-MM-DDTHH:MM:SSZ`, never earlier than the previous entry |
| `role` | string | yes | `owner`, `agent` or `auditor` |
| `type` | string | yes | one of the types in the table above |
| `commitment` | hex | yes | `SHA-256(salt ‖ canonical({text, claims, attachments}))`, salt = 32 random bytes |
| `attachments` | list of hex | yes | sorted, unique SHA-256 of every attached file and every claim's evidence file |
| `prev` | hex | yes | `hash` of the previous entry; 64 zeros for `seq` 1 |
| `corrects`, `audits` | hex | yes, when present | `hash` of an earlier entry |
| `signers_sha256` | hex | yes, when present | SHA-256 of `keys/allowed_signers`; on `genesis` and `keys` |
| `code_sha256` | hex | yes, when present | SHA-256 of `eilikrineia.py`; on `genesis` and `code` |
| `predecessor` | object | yes, when present | `{version, entries, head}` of a ledger taken over; on `genesis` only |
| `hash` | hex | — | `SHA-256(canonical(the hashed fields present))` |
| `signature` | string | — | `ssh-keygen -Y sign -n eilikrineia` over the ASCII bytes of `hash`, no newline |

### Verification

A verifier MUST report a problem when any of these fails, and the ledger is valid only with no problem:

1. Entry 1 has `type` `genesis` and `role` `owner`.
2. `keys/allowed_signers` hashes to the `signers_sha256` of the last entry that carries one.
3. For every entry: `seq` is its position; `prev` is the previous `hash`; `hash` recomputes; `time` is not earlier
   than the previous `time`; `corrects` and `audits` point to earlier hashes; owner-only types are signed by `owner`
   and auditor-only types by `auditor`.
4. `ssh-keygen -Y verify -I <role> -n eilikrineia -O verify-time=<time>` accepts the signature against
   `keys/allowed_signers`, so a key counts only inside its `valid-after` / `valid-before` window.
5. With the private folder (`verify --private`): every commitment recomputes from its text and salt; every vault
   copy hashes to its own name; every excerpt re-cut from the vault hashes to its recorded `excerpt_sha256`.

### Known gap of protocol 1 verifiers

A 1.0.0 verifier does not check that `type` is known and hashes only the fields listed above. In a scratch ledger,
an entry with an unknown type and an extra field verifies ok, and editing the extra field after signing still
verifies ok (ledger entry #70). A ledger that uses anything from protocol 2 MUST therefore be verified by a
protocol 2 verifier; a 1.0.0 verifier is not evidence about it.

---

## Protocol 2 (draft, not implemented)

Status: draft for review. Nothing here is implemented; the program still writes and verifies protocol 1. Each
addition below names the problem it solves and reuses protocol 1 where it can. Items marked [OPEN] wait for the
owner's decision.

### 2.1 Versioning and fail-closed verification

- A protocol 2 entry MUST carry `protocol: 2`. An entry without `protocol` is protocol 1.
- The hash of a protocol 2 entry MUST cover every top-level field except `hash` and `signature` (not a fixed list),
  so that no field can be added or edited without breaking the hash.
- A protocol 2 verifier MUST report as a problem any unknown `type`, any unknown top-level field, and any
  `protocol` value it does not implement.
- Downgrade is forbidden: after the first protocol 2 entry, every later entry MUST be protocol 2.
- The first protocol 2 entry MUST be signed by the owner (a `code` entry pinning a protocol 2 verifier), so the
  switch is rooted in the owner like every other change of rules.
- A 1.0.x patch SHOULD make protocol 1 verifiers fail closed on unknown types and fields, which shrinks the gap
  described above for anyone who has not upgraded.

### 2.2 Witness quorum (`witness_cosign`)

Problem: the witness of protocol 1 is a file in another OS account; its evidence lives outside the ledger, and a
single operator can still show different heads to different readers.

- New role pattern `witness-<id>`: each witness has its own key line in `keys/allowed_signers`, added by an owner
  `keys` entry like any key.
- New type `witness_cosign`, signed by a witness role, with `audits` set to the head hash it saw. No new field: the
  existing `audits` field already means "this entry vouches for that hash".
- New public field `policy` on `genesis` and `decision` entries: `{"witness_quorum": N, "witnesses": [ids]}`. The
  verifier reports every head not cosigned by at least `N` distinct listed witnesses after the policy's entry.
- The witness's own file and its account separation stay deployment practice, not protocol.

### 2.3 Scoped agent keys (`grant`)

Problem: an agent key today may record every agent type at any time its key is valid.

- Time windows already exist: `valid-after` and `valid-before` in `keys/allowed_signers`, enforced by
  `ssh-keygen -O verify-time`. Protocol 2 adds no second window.
- New public field `scopes` on `keys` entries: `{"<principal>": ["measured", "run", ...]}`. A verifier reports an
  entry whose type is outside its signer's scope at that time. A principal absent from `scopes` keeps the protocol
  1 permissions.
- Rule from the brief, "entry time is not later than the witness time": satisfied by 2.2, since a cosign is an entry
  later in the chain and `time` never decreases.

### 2.4 Memory seals (convention, no wire change)

Problem: agent memory files can be edited or rolled back between sessions without trace.

- A seal is a `measured` entry whose attachment is the memory file (its SHA-256 is public in `attachments`) and
  whose private body says `{"event": "load" | "save", "path", "byte_len", "session_id"}`.
- A seal check is a later `measured` entry with an `equals` claim comparing the current file's SHA-256 to the sealed
  one. A mismatch is recorded, never hidden; refusing to load is the loader's policy, not the ledger's.

### 2.5 Tool calls (convention, no wire change)

`tool_call` from the brief is a `run` entry whose attachments are the arguments, the result and the files read or
written, each committed by hash. Nothing new is needed on the wire.

### 2.6 Receipts (bundle format, no new entry type)

Problem: a third party must check, without trusting the operator, that a source existed with given bytes and that
an excerpt was found in it at a given time.

- A receipt is a portable bundle: the public entry, its revealed private body (`reveal`: text, salt, claims), the
  excerpt, and optionally the source file. Anyone recomputes the commitment, re-cuts the excerpt from the source,
  checks `excerpt_sha256`, re-runs the claim predicate, and verifies the chain and its timestamp.
- Status is derived by the checker, never asserted: the claim passes (`located_and_matched`), the locator does not
  fit the source (`not_located`), or the excerpt differs (`mismatch`). A receipt never states that a source does not
  exist, only that the method did not locate it.
- Every receipt carries the non-guarantees of this protocol: existence and literal text at time T only, never
  relevance, interpretation or current validity.
- [OPEN] Public receipt fields. Recommendation: none. Keeping `source_sha256` and `status` inside the commitment
  until a receipt is revealed keeps the operator blind; a public source hash would let anyone confirm which public
  document a client cited. The cost: a receipt cannot be found by searching the public chain, only by its bundle.

### 2.7 Reserved

`provider_attestation` is reserved for signed model outputs, if a vendor ever ships them. Until it is specified,
a protocol 2 verifier MUST treat it as an unknown field.

### 2.8 Canonical JSON in protocol 2

[OPEN] Two ways to close the gap with RFC 8785: keep `canonical()` and refuse floats and non-ASCII keys at write
time (no change for existing entries), or switch protocol 2 hashing to full JCS. Recommendation: refuse at write
time; on the allowed domain both are byte-identical, so there is nothing to migrate.
