# Protocol

Rules for any agent (Claude, Codex, Grok, Hermes or other) that writes to this ledger. The program refuses what
breaks the mechanical rules; the auditor judges the rest.

## Roles

| Role | Who | May record |
|---|---|---|
| `owner` | the person; key protected by a passphrase, out of the agent's reach (see Trust boundary) | `genesis`, `keys`, `code`, `decision`, and any other type |
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

This section describes protocol 1 as `eilikrineia.py` 1.0.1 implements it. The key words MUST, MUST NOT, SHOULD and
MAY are to be read as described in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in all capitals.
The protocol version is independent of the program's SemVer version.

### Layout

| Path | Public | Content |
|---|---|---|
| `chain/NNNNNN.json` | yes | one entry per file, `NNNNNN` = `seq` zero-padded to 6 digits |
| `keys/allowed_signers` | yes | current role keys, ssh-keygen ALLOWED SIGNERS format, namespace `eilikrineia` |
| `keys/allowed_signers.<sha256>` | yes | a copy of every key list the owner signed, named by its SHA-256 (from 1.0.1) |
| `stamps/NNNNNN.txt`, `.ots` | yes | `eilikrineia\nseq N\nhead H\n` and its OpenTimestamps proof |
| `private/texts/NNNNNN.json` | no | `{seq, hash, salt, text, claims, attachments}` |
| `private/vault/<sha256>.gz` | no | gzip copy of an evidence file, named by the SHA-256 of the original bytes (older copies: `<sha256>`, uncompressed) |

### Canonical JSON

`canonical(x)` is UTF-8 JSON with keys sorted, no insignificant whitespace and no escaping of non-ASCII characters
(Python `json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`). On the domain used by
protocol 1 (integers below 2^53, strings, lists, objects with ASCII keys, no floating-point numbers) this output is
identical to RFC 8785 (JCS); it differs from JCS only for floating-point numbers and for keys outside the Basic
Multilingual Plane. This repository's own ledger stays inside the domain (ledger entry #71). Writers MUST NOT put
floating-point numbers or non-ASCII keys in any hashed or committed object; 1.0.1 does not enforce this yet (an
`equals` claim accepts any JSON value).

### Entry

| Field | Type | Hashed | Meaning |
|---|---|---|---|
| `seq` | integer | yes | 1, 2, 3, ... without gaps |
| `time` | string | yes | UTC, `YYYY-MM-DDTHH:MM:SSZ`, declared by the writer, never earlier than the previous entry |
| `role` | string | yes | `owner`, `agent` or `auditor` |
| `type` | string | yes | one of the types in the table above |
| `commitment` | hex | yes | `SHA-256(salt ‖ canonical({text, claims, attachments}))`, salt = 32 random bytes |
| `attachments` | list of hex | yes | sorted, unique SHA-256 of every attached file and every claim's evidence file |
| `prev` | hex | yes | `hash` of the previous entry; 64 zeros for `seq` 1 |
| `corrects`, `audits` | hex | yes, when present | `hash` of an earlier entry; `audits` marks an auditor alarm about it |
| `signers_sha256` | hex | yes, when present | SHA-256 of `keys/allowed_signers`; only on owner `genesis` and `keys` |
| `code_sha256` | hex | yes, when present | SHA-256 of `eilikrineia.py`; only on owner `genesis` and `code` |
| `predecessor` | object | yes, when present | `{version, entries, head}` of a ledger taken over; only on owner `genesis` |
| `hash` | hex | — | `SHA-256(canonical(the hashed fields present))` |
| `signature` | string | — | `ssh-keygen -Y sign -n eilikrineia` over the ASCII bytes of `hash`, no newline |

### Key list in force

The **well-linked prefix** of a chain ends before the first entry whose `seq` is not its position, whose `prev` is
not the previous `hash`, or whose `hash` does not recompute. Inside it, the key list in force at entry 1 is the one
the owner genesis commits (the trust root); at every later entry it is the list committed by the last owner
`genesis` or `keys` entry before it **whose signature verifies against the list in force at that entry**. The
current `keys/allowed_signers` is never trusted by itself: a key planted in it must not be able to sign the entry
that would approve it. Consequently an owner key is replaced by a `keys` entry signed with the old owner key.
A key list is available when it is the current file or its copy `keys/allowed_signers.<sha256>`.

The well-linked prefix also ends at an entry that is not a JSON object or whose `time` is earlier than the previous
one, so an owner entry backdated into a retired key's window never counts.

The pinned auditor code is the `code_sha256` of the last owner `genesis` or `code` entry of the well-linked prefix
whose signature verifies against the key list in force at that entry. The auditor job adopts new code only when
its SHA-256 equals the pinned one (`pinned-ok`), the whole chain is well linked, and every entry the witness has
already recorded is present and unchanged.

**Trust anchor.** Everything above is computed from `chain/` and `keys/`, which the agent's account can write; a
genesis signed by an attacker key, with its key list planted, would be self-consistent. The anchor is therefore
outside those folders: for the auditor, the witness file in its own account (which holds the hash of entry 1 and
of every later entry it saw); for an outside reader, the genesis hash obtained from a source the operator does not
control (an archived release, a published timestamp, the owner). A verifier SHOULD compare entry 1's hash with such
an anchor.

### Verification

A verifier MUST report a problem when any of these fails, and the ledger is valid only with no problem:

1. Entry 1 has `type` `genesis` and `role` `owner`.
2. `keys/allowed_signers` hashes to the key list committed last, as defined above.
3. For every entry: `seq` is its position; `prev` is the previous `hash`; `hash` recomputes; `time` is not earlier
   than the previous `time`; `corrects` and `audits` point to earlier hashes; owner-only types are signed by `owner`
   and auditor-only types by `auditor`.
4. For every entry: `type` and `role` are known; there is no field besides the hashed ones, `hash` and
   `signature`; `signers_sha256`, `code_sha256` and `predecessor` appear only where the table above allows them.
5. `ssh-keygen -Y verify -I <role> -n eilikrineia -O verify-time=<time>` accepts the signature against the key
   list in force at the entry (or the current list past the well-linked prefix), so a key counts only inside its
   `valid-after` / `valid-before` window.
6. With the private folder (`verify --private`): every commitment recomputes from its text and salt; every vault
   copy an entry references hashes to its own name; every excerpt re-cut from the vault hashes to its recorded
   `excerpt_sha256`.

### Excerpts, as implemented

Two implementations agree on `excerpt_sha256` only if they cut identically. Protocol 1 cuts the vault copy decoded
as UTF-8 with invalid bytes replaced by U+FFFD:

- `{"lines": [a, b]}`: Python `str.splitlines()` (which also splits on `\x0b \x0c \x1c-\x1e \x85 U+2028 U+2029`),
  lines `a` to `b` inclusive, joined by `\n`;
- `{"json": "/p/q"}`: split on `/`, empty parts dropped, integer index for lists (no RFC 6901 `~0`/`~1` escapes),
  the node serialized with `json.dumps(node, ensure_ascii=False, sort_keys=True)` (default separators, not
  canonical JSON);
- `{"all": true}`: the whole text.

Predicates follow Python semantics: `number` uses `re.search` (`\d` matches any Unicode digit) and `int()`;
`equals` compares parsed JSON with `==` (so `true == 1 == 1.0`). An independent verifier MUST reproduce these.

### Trust boundary of protocol 1

Protocol 1 and the single-file tool hold only where the agent cannot reach the owner's private key or passphrase,
the auditor's OS account, or the witness file. An agent that can become root on the machine (for example, through
an administrator password kept where its account can read it) can sign as the owner, rewrite the witness file,
and change the code the auditor runs; three adversarial reviews (2026-10-29) found no patch that survives an
adversary on the same machine. Where that boundary does not hold, a protocol 1 ledger is bookkeeping kept by a
cooperative agent, not proof. Protocol 2 is designed for a hostile agent machine.

### What a 1.0.1 verifier does not check

- The presence and format of every field (`time` format, `attachments` sorted and unique, a missing `commitment`).
- That the public `attachments` equal the set derived from the private body.
- The OpenTimestamps proofs in `stamps/` (verify them with `ots verify`).
- An upper bound on `time`: an entry dated in the future is accepted, and every honest entry after it then reads
  as backdated, which stops `audit` and `publish` until the owner intervenes.
- Concurrent writers: `record` takes no lock.

### Defect fixed in 1.0.1

In 1.0.0 the pinned key list and the pinned code were taken from the last entry carrying the field, whatever its
role, type or signature, and a verifier accepted unknown types and fields. A raw unsigned file in `chain/` made
`pinned-ok` accept arbitrary code, and an agent-signed entry could commit a key list with a planted owner key
(ledger entries #70 and #75). A first fix still trusted a genesis found in `chain/` and allowed cutting the tail
back to older code (entry #77); 1.0.1 anchors both in the witness. Do not use a 1.0.0 verifier.

---

## Protocol 2 (draft, not implemented)

Status: draft for review, revised after an adversarial review and after the decision that the agent's machine is
hostile (both 2026-10-29). Nothing here is implemented; the program still writes and verifies protocol 1. Each
addition names the problem it solves and reuses protocol 1 where it can. Items marked [OPEN] wait for the owner's
decision.

### 2.0 Threat model

Protocol 2 assumes that the machine where an agent runs is hostile, including root. On that machine the agent can
read and write every file, run any code, delete hooks and local checks, show the owner anything on screen, withhold
entries, and hand a signing key any bytes at the moment the owner approves. A guarantee of protocol 2 holds while
trusting only four things that machine never holds:

1. **The owner's signing device** (2.3), which shows what it signs.
2. **Witnesses with a quorum** (2.2), run by operators independent of each other and off the agent's machine.
3. **Evidence runners** (2.4) that the agent does not operate.
4. **The verifier**, pinned by the SHA-256 of a DOI-archived release that the reader obtains out of band. A reader
   never runs code because the ledger names it.

What root on the agent's machine can still do, and what protocol 2 makes of it:

| Attack from the agent's machine | Answer |
|---|---|
| Write evidence files and cite them | The evidence is `self_reported` (2.4); "tested" needs runner output |
| Delete local hooks and checks | Enforcement lives where the work is consumed (2.5) |
| Make the owner sign other bytes | The signing device computes and displays what it signs (2.3) |
| Rewrite, cut or fork the ledger | Witnesses refuse a head that does not extend the last one they cosigned (2.2) |
| Withhold an entry | Not prevented: omission is visible only as absence |
| Read private bodies stored on that machine | Not prevented: confidentiality holds only where the bodies are kept |

Developing this tool is a separate concern from using it: agents that build the verifier are a supply-chain risk,
answered by a protected default branch, releases signed by the owner's signing device, and adversarial review.

### 2.1 Versioning and fail-closed verification

- A protocol 2 entry MUST carry `protocol: 2`. An entry without `protocol` is protocol 1; an explicit
  `protocol: 1` is invalid (protocol 1 does not hash that field).
- The hash of a protocol 2 entry MUST cover every top-level field except `hash` and `signature`. An absent field
  and a `null` field are different; writers MUST omit a field rather than set it to `null`. A JSON object with a
  duplicate key MUST be rejected.
- Fields introduced by protocol 2 are valid only on protocol 2 entries; on a protocol 1 entry they are unknown
  fields (protocol 1 would not hash them).
- A protocol 2 verifier MUST report any unknown `type`, unknown top-level field, `protocol` value it does not
  implement, and any field on a type that does not allow it (rule 4 of protocol 1 carries over).
- Each role has a closed list of types: `owner` (`genesis`, `keys`, `code`, `decision`, and agent types), `agent`
  (`measured`, `assertion`, `opinion`, `correction`, `run`), `auditor` (`audit`, `checkpoint`), `witness-<id>`
  (`witness_cosign` only), `runner-<id>` (`attested_run` only, 2.4).
- Downgrade is forbidden: after the first protocol 2 entry, every later entry MUST be protocol 2.
- The first protocol 2 entry MUST be an owner `code` entry naming the protocol 2 verifier release (its SHA-256 and
  DOI). It is a statement for readers, not an instruction to install: no component adopts code because the ledger
  names it, and a reader pins the verifier from the release itself (2.0).
- A protocol 1 verifier reports every protocol 2 entry as altered, since it does not hash `protocol`; a 1.0.x
  release SHOULD say "unsupported protocol" instead.

### 2.2 Witness quorum (`witness_cosign`)

Problem: the protocol 1 witness is a file in another OS account, outside the ledger; one operator can still show
different heads to different readers.

- Witnesses run off the agent's machine, each under an operator independent of the others; the operator of the
  service is at most one of them. The protocol 1 witness in another OS account of the same machine does not count
  toward a quorum.
- Each witness has its own principal `witness-<id>` and its own key line, added by an owner `keys` entry. Principals
  MUST be exact names: no wildcards, no comma lists, no `cert-authority`.
- New type `witness_cosign` with a new field `cosigns`, which MUST equal `prev`: the witness vouches exactly for
  the head it extends, never for entries it did not see. (`audits` is not reused: in protocol 1 it marks an alarm.)
  A cosign has no private body; its `commitment` is 64 zeros and `verify --private` skips it.
- A witness keeps state and cosigns only a head that extends the last head it cosigned; it takes the cosign `time`
  from its own clock and refuses to cosign a head whose `time` is later than its clock plus a tolerance [OPEN:
  tolerance, suggested 5 minutes].
- New public field `policy` on protocol 2 owner `genesis` and `decision` entries:
  `{"witness_quorum": N, "witnesses": ["<id>", ...]}`. Entries after the last head cosigned by at least `N` listed
  witnesses with distinct keys form the **unwitnessed tail**; a verifier reports its length rather than failing.
- Trust anchor outside the ledger: the owner key alone cannot prevent an owner who runs the service from creating
  witness keys of his own. A verifier MUST compare the owner key fingerprint and the witness key fingerprints with a
  source the operator does not control (for example, the witness's own published key, or a fingerprint printed on
  the receipt and checked against the client's records). A reader MUST take the head from a quorum of witnesses, never
  from the operator or the agent's machine, so a truncated copy that ends before a `policy` entry is detected.

### 2.3 Owner signing device

Problem: root on the agent's machine cannot extract a key from hardware, but it can hand the key different bytes at
the moment the owner approves. A touch proves presence, not content: with a touch-only key, every approval gives a
root agent one legitimate owner signature over bytes of its choice.

- The owner key MUST NOT be reachable from the agent's machine: not as a file, not through a forwarded SSH agent.
  It lives on a signing device: a phone app with the key in the Secure Enclave or StrongBox, or a hardware signer
  with its own display.
- The device receives the entry's fields, never a hash or a byte string to sign. It MUST parse the fields, compute
  the canonical bytes and the `hash` itself, render the display from the same parsed fields, and sign only those
  bytes. Display and signature then bind to the same data, whatever the host sent.
- For an entry with a private body (`genesis`, `decision`, and any owner entry with text), the device also receives
  the text and salt, recomputes `commitment`, and displays the text. The owner never signs a commitment
  without seeing its text.
- The display MUST show `seq`, `type`, `role`, `time` and the start of `prev`, and per type:
  - `keys`: each principal added, removed or changed, with its key fingerprint, validity window and scopes (2.6).
    The device keeps its own copy of the last key list it signed and computes the difference against that copy, not
    against a list the host provides; if the host's base list differs from the device's copy, the device warns and
    shows both.
  - `code`: the release version, its SHA-256 and the release URL; the device SHOULD fetch the release over its own
    network and compare the hash.
  - any other type: the text and the claims.
- The device keeps the last head it signed (`seq`, `hash`) and warns before signing an entry whose `seq` is not
  greater, which is how a fork of the ledger would reach the owner.
- Signatures stay in the SSHSIG format of protocol 1, which carries `ecdsa-sha2-nistp256` keys as held by the
  Secure Enclave and StrongBox: no wire change.
- A verifier cannot tell which device produced a signature. This section binds implementations of the signer, and
  a deployment that keeps the owner key on the agent's machine has none of the guarantees of 2.0.
- [OPEN] Transport between the agent's machine and the device (QR code, push through the service). The transport
  is untrusted either way, since the device recomputes everything it signs.

### 2.4 Evidence runners and evidence tiers

Problem: in protocol 1 a `measured` entry proves that a file says something, not that a command produced it. The
agent can write the file it cites.

- A runner is a principal `runner-<id>` with role `runner`, whose key line is added by an owner `keys` entry. It
  runs off the agent's machine (a CI job, the service's runner), and its key never reaches that machine. Role
  `runner` records one type: `attested_run`.
- The runner fetches its input itself, by commit id, from the protected remote. It never accepts a tree uploaded
  from the agent's machine.
- New type `attested_run` with new public fields:
  - `input`: `{"repo": "<URL>", "commit": "<id>", "tree": "<git tree id>"}`;
  - `command`: the exact command line it ran;
  - `exit_code` (integer) and `duration_ms` (integer);
  - `environment`: the runner version and the digest of the image it ran in.
  Its standard output and standard error are attachments, committed by hash like any other evidence; its private
  body holds them in the vault.
- The tier of a claim is **derived by the verifier**, never written by an agent: a claim is `attested` when the
  SHA-256 of its evidence file equals an output attachment of an earlier `attested_run` signed by a runner key in
  force; otherwise it is `self_reported`. An entry is `attested` only when every claim in it is. A field that
  declares a tier is an unknown field and is rejected (2.1).
- `attested` means: this runner, on this commit, ran this command and this was the output. It does not mean that
  the command tests what the agent says it tests.
- New public field in `policy` (2.2): `"commands": {"<name>": "<command line>"}`, the commands the owner accepts as
  checks for the gate of 2.5.
- [OPEN] More than one runner per command, so that a single compromised runner key cannot forge a passing run.

### 2.5 Enforcement at the point of use

Problem: root on the agent's machine deletes local hooks and the checks they run. Any enforcement on that machine
is advisory.

- Enforcement lives where the work is consumed: a required status check on the protected branch, enforced by the
  repository host, and the service, which refuses to issue a receipt (2.9). Local hooks stay useful as fast
  feedback, never as enforcement.
- The check fails closed. It passes for a commit only when:
  1. for every command in the owner's `policy`, an `attested_run` on that exact commit has `exit_code` 0;
  2. those entries lie inside the witnessed part of the ledger (2.2), read from the witnesses, not from the agent's
     machine;
  3. no `audit` alarm is newer than the last owner `decision` that resolves it.
- The agent MUST NOT hold credentials that can change the branch protection or the required checks; a deployment
  where it does has no gate.

### 2.6 Scoped agent keys (`grant`)

Problem: an agent key may record every agent type at any time it is valid.

- Time windows already exist: `valid-after` and `valid-before` in the key list. Because `time` is declared by the
  writer, an expiry is only as strong as the witness clock of 2.2.
- New public field `scopes` on protocol 2 owner `keys` entries: `{"<principal>": ["measured", "run", ...]}`. The
  types a principal may record are the intersection of its scope with its role's types. A scope stays in force
  until a later `keys` entry replaces it; a `keys` entry without `scopes` keeps the previous scopes.
- Scopes apply per principal; to scope one key, give it its own principal (`agent-<id>`, role `agent`).

### 2.7 Memory seals (convention, no wire change)

Problem: agent memory files can be edited or rolled back between sessions without trace.

- A seal is a `measured` entry that attaches the memory file (its SHA-256 becomes public in `attachments`); its
  private text states `{"event": "load" | "save", "path", "byte_len", "session_id"}` as JSON.
- A seal check attaches the file again; the mechanical comparison is between the two public `attachments` hashes.
  A mismatch is recorded, never hidden; refusing to load is the loader's policy.

### 2.8 Tool calls (convention, no wire change)

`tool_call` from the brief is a `run` entry whose attachments are the arguments, the result and the files read or
written, each committed by hash.

### 2.9 Receipts (bundle format, no new entry type)

Problem: a third party must check, without trusting the operator, that a source existed with given bytes and that
an excerpt was found in it at a given time.

- A receipt is a portable bundle: the public entry, its whole private body (text, salt, claims and attachments;
  1.0.1 `reveal` returns only text and salt and must be extended), the excerpt, and optionally the source file.
  Anyone recomputes the commitment, re-cuts the excerpt, checks `excerpt_sha256`, re-runs the claim predicate, and
  verifies the chain, its witnesses and its timestamp.
- Status is derived by the checker, never asserted: the claim passes (`located_and_matched`), the locator does not
  fit the source (`not_located`), or the excerpt differs (`mismatch`). A receipt never states that a source does
  not exist, only that the method did not locate it.
- "At time T" means: not after the OpenTimestamps time of a later head; the entry's own `time` is self-declared.
- Every receipt carries the non-guarantees of this protocol: existence and literal text, never relevance,
  interpretation or current validity.
- Privacy, measured against protocol 1: the public `attachments` field already exposes the SHA-256 of every
  evidence file, so anyone holding a public document can confirm which entries cite it, and the private body stores
  absolute file paths. [OPEN] Recommendation for protocol 2: publish `SHA-256(salt_i ‖ sha256)` per attachment
  instead of the raw hash, and store base names only. Cost: none for verification, which already needs the
  revealed body to check a vault copy.

### 2.10 Reserved

`provider_attestation` is reserved for signed model outputs. Until specified it is an unknown field.

### 2.11 Canonical JSON in protocol 2

[OPEN] Keep `canonical()` and refuse floats and non-ASCII keys at write time, or switch to full RFC 8785.
Recommendation: refuse at write time; on the allowed domain both are byte-identical, so nothing migrates.
