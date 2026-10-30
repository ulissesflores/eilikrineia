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
hostile (both 2026-10-29), and again after two adversarial reviews of that revision (2026-10-30). Nothing here is
implemented; the program still writes and verifies protocol 1. Each
addition names the problem it solves and reuses protocol 1 where it can. Items marked [OPEN] wait for the owner's
decision.

### 2.0 Threat model

Protocol 2 assumes that the machine where an agent runs is hostile, including root. On that machine the agent can
read and write every file, run any code, delete hooks and local checks, show the owner anything on screen, withhold
or reorder entries, push ordinary commits, and hand a signing key any bytes at the moment the owner approves. It
does not hold the owner's signing device, a witness key or a runner key, and it cannot rewrite the protected
remote's history. A guarantee of protocol 2 holds while trusting these anchors, which that machine never holds:

1. **The owner's signing device** (2.3), which computes and shows what it signs.
2. **Witnesses with a majority quorum** (2.2), run by operators independent of each other and off the agent's
   machine.
3. **Evidence runners** (2.4) that the agent does not operate and whose jobs it cannot define.
4. **The verifier**, pinned by the SHA-256 of a DOI-archived release whose signature the reader checks against an
   owner fingerprint obtained out of band. A reader never runs code because the ledger names it.

Protocol 2 also depends on the repository host, which enforces branch protection and the required check of 2.5, on
the operator of the gate app of 2.5, and on OpenTimestamps for an upper bound on time (2.9). Each dependency is named
where it is used.

What root on the agent's machine can still do, and what protocol 2 makes of it:

| Attack from the agent's machine | Answer |
|---|---|
| Write evidence files and cite them | The evidence is `self_reported`; `attested` needs a named run of an owner-listed command (2.4) |
| Change the tests so they pass without checking | Narrowed, not prevented: code under test runs in the harness's process (2.5) |
| Delete local hooks and checks, or post the status itself | The gate's own app is the only source of the required check (2.5) |
| Make the owner sign other bytes | The device renders every field and computes every hash it signs (2.3) |
| Register a runner or witness key it generated | Fingerprints come from a source the owner names on the device (2.3) |
| Rewrite, cut or fork the witnessed ledger | One sequencer orders entries; a majority quorum cosigns (2.2) |
| Withhold, bury or starve an owner entry | The device submits it; the sequencer reserves its head on request (2.2) |
| Withhold its own entries | Not prevented: omission is visible only as absence |
| Read private bodies stored on that machine | Not prevented: confidentiality holds only where the bodies are kept |

Developing this tool is a separate concern from using it: agents that build the verifier are a supply-chain risk,
answered by a protected default branch, releases signed by the owner under a namespace other than the ledger's
(2.3), and adversarial review.

### 2.1 Versioning and fail-closed verification

- A protocol 2 entry MUST carry `protocol: 2`. An entry without `protocol` is protocol 1; an explicit
  `protocol: 1` is invalid (protocol 1 does not hash that field).
- The hash of a protocol 2 entry MUST cover every top-level field except `hash` and `signature`. An absent field
  and a `null` field are different; writers MUST omit a field rather than set it to `null`. A JSON object with a
  duplicate key MUST be rejected.
- A protocol 2 entry MUST carry a hashed `principal`, the exact name of the key line that signs it, and MUST NOT
  carry `role`; type rules are checked against the principal's role. The signature is verified with
  `ssh-keygen -Y verify -I <principal>`. Principal names MUST match `[a-z0-9-]+`, and the role is
  the part before the first `-`: `owner`, `agent` or `agent-<id>`, `auditor` or `auditor-<id>`, `witness-<id>`, `runner-<id>`.
  Key lines MUST name exact principals: no wildcards, no comma lists, no `cert-authority`.
- Fields introduced by protocol 2 are valid only on protocol 2 entries; on a protocol 1 entry they are unknown
  fields (protocol 1 would not hash them).
- A protocol 2 verifier MUST report any unknown `type`, unknown top-level field, `protocol` value it does not
  implement, and any field on a type that does not allow it (rule 4 of protocol 1 carries over).
- Each role has a closed list of types: `owner` (`genesis`, `keys`, `code`, `decision`, and agent types), `agent`
  (`measured`, `assertion`, `opinion`, `correction`, `run`), `auditor` (`audit`, `checkpoint`), `witness`
  (`witness_cosign`), `runner` (`attested_run`).
- Downgrade is forbidden: after the first protocol 2 entry, every later entry MUST be protocol 2.
- A new protocol 2 ledger starts with an owner `genesis` that commits the complete key list. In a ledger migrated
  from protocol 1, the first protocol 2 entry MUST be an owner `keys` entry, signed on the device (2.3), that
  commits the complete key list, shown in full as additions: every principal not in it loses force, including the
  protocol 1 `owner` and `auditor`, whose keys lived on the agent's machine.
- Next comes an owner `code` entry with `code_sha256` and a hashed `release` field
  `{"version": "<x.y.z>", "url": "<release URL>", "doi": "<DOI>"}`, naming the protocol 2 verifier. It is a
  statement for readers, not an instruction to install: no component adopts code because the ledger names it, and
  a reader pins the verifier from the release itself (2.0). The protocol 1 auditor job, which runs
  pinned code in another OS account of the same machine, is not part of protocol 2.
- A protocol 1 verifier reports every protocol 2 entry as altered, since it does not hash `protocol`; a 1.0.x
  release SHOULD say "unsupported protocol" instead.

### 2.2 Witness quorum (`witness_cosign`) and policy

Problem: the protocol 1 witness is a file in another OS account of the same machine; one operator can still show
different heads to different readers, and whoever forwards entries decides what the witnesses see.

**Witnesses.**
- Witnesses run off the agent's machine, each under an operator independent of the others; the operator of the
  service is at most one of them. The protocol 1 witness does not count toward a quorum.
- Each witness has its own principal `witness-<id>`, whose key is generated on the witness and added by an owner
  `keys` entry under the provenance rule of 2.3.
- New type `witness_cosign` with a new field `cosigns`, which MUST equal `prev`. A cosign vouches for its head and
  every entry before it; another witness cosigns by extending that cosign. (`audits` is not reused: in protocol 1
  it marks an alarm.) A cosign has no private body; its `commitment` is 64 zeros and `verify --private` skips it.
- A witness keeps state. Before it cosigns, it MUST run on every entry between its last cosigned head and the new
  one every check a protocol 2 verifier makes without the private folder (sequence, links, hash, signature against
  the key list in force, types per role and scope, fields, policy validity, time), and refuse unless the new head
  extends the last. A private-body failure found later is reported per entry and does not invalidate the ledger.
- A witness's first head MUST come from the owner's device or from a quorum of the existing witnesses, never from
  the agent's machine, and MUST be signed by an owner fingerprint the witness obtained from the owner out of band. Entries before the first quorum-cosigned head are reported as unwitnessed protocol 1
  history: a protocol 1 owner key lived inside the boundary that protocol 2 no longer trusts.
- Time: the cosign `time` is the later of the witness's clock and the head's `time`. A witness refuses a head that
  contains an entry dated later than its clock plus a tolerance, or earlier than its last cosign; and no entry's
  `time` may be earlier than the `time` of the last `witness_cosign` before it. [OPEN: tolerance, suggested 5
  minutes.]

**Ordering and owner entries.**
- The `policy` MUST name one listed witness as `sequencer`. Every entry, including the other witnesses' cosigns,
  enters the chain only in the order the sequencer cosigns it, and the other witnesses MUST cosign only heads the
  sequencer has cosigned. The sequencer can stall the ledger, not forge it, and a sequencer that signs two
  conflicting heads is caught by the others.
- Writers submit entries to the sequencer, built on its latest head; an entry on an older head is rejected as
  stale and its writer rebuilds it.
- Owner entries and runner entries are submitted by the device or the runner itself (2.3, 2.4). An owner entry
  whose `prev` is the sequencer's latest head MUST be sequenced before any other entry on that head; an owner entry
  on an older head is rejected as stale, and the device shows that and re-signs.
- On a request authenticated by the owner's device, the sequencer MUST reserve its current head for a bounded time
  and accept no other entry on it, so the agent cannot starve the owner by advancing the head. [OPEN: duration.]

**Policy.**
- New public field `policy` on protocol 2 owner `genesis` and `decision` entries:
  `{"witness_quorum": N, "witnesses": [...], "sequencer": "<id>", "commands": {...}, "runners": {...},
  "protected_paths": [...]}`. The last three are defined in 2.4 and 2.5.
- `witness_quorum` MUST be greater than half the number of listed witnesses; a verifier rejects a policy with a
  smaller quorum, with no witnesses, or with an empty `commands`.
- A new `policy` takes effect only when a head containing it is cosigned by a quorum of the previous policy and a
  quorum of the new one; until then the previous policy stays in force. A verifier rejects a policy that lists a
  witness or sequencer without a key in force.
- The first policy takes effect when a quorum of its own witnesses cosigns a first head delivered by the device.
  Recovery from a quorum that can no longer cosign is a new genesis with `predecessor`.
- Entries after the last head cosigned by a quorum of the policy in force form the **unwitnessed tail**; a verifier
  reports its length rather than failing.

**Readers.**
- A reader MUST take the head from the witnesses, never from the operator or the agent's machine: it queries every
  listed witness it can reach and requires a quorum. It MUST reject when two conflicting heads each carry a quorum,
  or when one witness has signed two conflicting heads; a head that never reached quorum is not a conflict.
- A verifier, and the gate of 2.5, MUST compare the owner, witness, runner and auditor key fingerprints with a source
  the operator does not control, named as in 2.3. A fingerprint on the receipt, or in records kept on the agent's
  machine, does not qualify.

### 2.3 Owner signing device

Problem: root on the agent's machine cannot extract a key from hardware, but it can hand the key different bytes at
the moment the owner approves. A touch proves presence, not content: with a touch-only key, every approval gives a
root agent one legitimate owner signature over bytes of its choice.

**Custody.**
- The owner key MUST NOT be reachable from the agent's machine: not as a file, not through a forwarded SSH agent.
  It lives on a signing device: a phone app with the key in the Secure Enclave or StrongBox, or a hardware signer
  with its own display.
- Signatures stay in the SSHSIG format of protocol 1, which carries `ecdsa-sha2-nistp256` keys as held by the
  Secure Enclave and StrongBox: no wire change.
- The device MUST use namespace `eilikrineia` only over an entry hash it computed itself. Release signatures MUST
  use another namespace (`eilikrineia-release`) and SHOULD use another key, so that a "release" whose content is an
  entry hash is never a valid ledger signature.

**What the device computes.**
- The device receives the entry's fields, never a hash or a byte string to sign. It MUST parse the fields, compute
  the canonical bytes and the `hash` itself, render the display from the same parsed fields, and sign only those
  bytes.
- For every hash field it MUST receive the underlying bytes, compute the hash itself, render from those bytes, and
  ignore any hash the host sent:
  - `commitment`: the text, salt, claims and attachments of the private body;
  - `signers_sha256`: the whole new key list;
  - `code_sha256`: the release file, fetched by the device over its own network from the `release` URL.
- A release signature (namespace `eilikrineia-release`) MUST cover only bytes the device fetched itself from a tag
  of a commit on the protected default branch; the device shows that commit id, and the bytes MUST equal an output
  of an `attested_run` of a listed build command on that commit.

**What the device shows.**
- It MUST render every top-level field of the entry and refuse to sign an entry with a field it cannot render.
- Text and claims in full, never truncated. It refuses control characters, bidirectional overrides, zero-width
  characters, and any character it cannot display.
- `keys`: each principal added, removed or changed, with its fingerprint, validity window and scopes (2.6),
  computed against the device's own copy of the last key list it signed (with no copy, the whole list as
  additions). If the host's base list differs from that copy, the device warns and shows both.
- Provenance of a new runner, witness or auditor key: the device MUST obtain the fingerprint over its own network
  from a source the owner entered on the device or that comes from the device's own list of operators, never from a
  source the host names, and show where it came from.
- `keys` at migration or bootstrap: the device MUST compute the key list in force at `prev` itself, from the quorum
  chain, never take it from the host.
- `reviewed` (2.5): the device MUST fetch that commit from the protected remote over its own network and render
  every protected path that changed since the previous `reviewed` commit.
- `policy`: the difference against the device's own copy of the last policy it signed.
- `decision` that resolves an alarm: the alarm text (2.5).

**Where the device signs.**
- The device fetches the quorum head from the witnesses over its own network and signs only an entry whose `prev`
  extends it. It submits the signed entry to the witnesses itself and shows it as pending until a quorum cosigns a
  head that contains it. An owner revocation therefore cannot be withheld by the agent.

**Scope.**
- A verifier cannot tell which device produced a signature. This section binds implementations of the signer, and
  a deployment that keeps the owner key on the agent's machine has none of the guarantees of 2.0.
- [OPEN] Transport between the agent's machine and the device (QR code, push through the service). The transport
  is untrusted either way, since the device recomputes everything it signs.

### 2.4 Evidence runners and evidence tiers

Problem: in protocol 1 a `measured` entry proves that a file says something, not that a command produced it. The
agent can write the file it cites.

**Runners.**
- A runner is a principal `runner-<id>`. Its key is generated on the runner and added by an owner `keys` entry
  under the provenance rule of 2.3. Role `runner` records one type: `attested_run`.
- The runner key MUST NOT be available to any job whose definition, workflow or image can be changed from a ref the
  agent can push. A CI job defined in the agent's own repository does not qualify.
- The runner MUST execute the command inside an isolation boundary with no access to the signing key, the signer's
  process or its output buffers; it captures standard output, standard error and the exit code from outside that
  boundary, and discards the boundary after each run. The command runs code the agent wrote.
- New public field in `policy` (2.2): `"runners": {"runner-<id>": "<image digest>"}`. A run counts only if its
  `environment` matches the digest pinned for its runner.
- New public field in `policy`: `"commands": {"<name>": "<command line>"}`. A runner MUST run only command lines
  listed there, byte for byte.
- The runner fetches its input itself, by commit id, from the protected remote. It never accepts a tree uploaded
  from the agent's machine. It submits its entry to the witnesses itself, so a failing run cannot be withheld.

**`attested_run`.** New type with new public fields:
- `input`: `{"repo": "<URL>", "commit": "<id>", "tree": "<git tree id>"}`;
- `command`: the exact command line it ran;
- `exit_code` (integer) and `duration_ms` (integer);
- `environment`: the runner version and the digest of the image it ran in.

Its standard output and standard error are attachments, committed by hash like any other evidence; its private
body holds them in the vault.

**Tiers.**
- The tier of a claim is **derived by the verifier**, never written by an agent. A claim is `attested` when its
  claim object names an `attested_run` by hash (`"run": "<hash>"`), that run is earlier, signed by a runner in force
  and counts under the policy, and the SHA-256 of the claim's evidence file equals one of that run's output
  attachments. Otherwise it is `self_reported`. An entry is `attested` only when every claim in it is. A field that
  declares a tier is an unknown field and is rejected (2.1).
- A verifier MUST report the run's `input.commit` and `command` next to the tier, so a claim about one commit that
  cites a run on another is visible.
- `attested` means: this runner, on this commit, ran this owner-listed command and this was the output. It does not
  mean that the command tests what the agent says it tests; 2.5 closes that gap only for the paths the owner
  protects.
- [OPEN] More than one runner per command, so that a single compromised runner key cannot forge a passing run.

### 2.5 Enforcement at the point of use

Problem: root on the agent's machine deletes local hooks and the checks they run, and anyone with write access to a
repository can set the state of a status check. Any enforcement on that machine is advisory.

- Enforcement lives where the work is consumed: a required status check on the protected branch, enforced by the
  repository host, and the service, which refuses to issue a receipt (2.9). Local hooks stay useful as fast
  feedback, never as enforcement.
- The required check MUST name the gate's own app as its only expected source, and no credential the agent holds
  may write statuses as that app. The app's credential follows the key rules of a runner (2.4), isolation included,
  and the gate runs the pinned verifier release. The agent MUST NOT hold credentials that can change the branch protection, the
  required checks or the rulesets; a deployment where it does has no gate.
- New public field in `policy` (2.2): `"protected_paths": ["<path or glob>", ...]`, the test harness and the files
  it trusts (test configuration, build scripts, interpreter start-up hooks).
- The check fails closed. It passes for a commit only when, reading entries from anywhere and checking them against
  a head taken from a quorum of witnesses (2.2):
  1. for every command in the policy, the latest `attested_run` on that exact commit, with `command` byte-equal to
     the policy's line, has `exit_code` 0;
  2. the set of files matching `protected_paths`, with their bytes, is identical to that of the last commit an owner
     `decision` names in the hashed field `reviewed: "<commit id>"`; with a non-empty `protected_paths` and no such
     decision, the check fails;
  3. those entries lie inside the witnessed part of the ledger;
  4. no `audit` alarm is unresolved. An alarm counts only when signed by an auditor principal that runs off the
     agent's machine under the key rules of a runner (2.4); it is resolved only by an owner `decision` carrying the
     hashed field `resolves: "<audit hash>"`, whose device displays the alarm (2.3).
- What a passing check means: the owner-listed commands exited 0 on that tree, run by a runner the owner
  registered, with the protected paths as the owner reviewed them. It does not mean that the tests ran or passed:
  code under test runs in the harness's process and can force the exit code. Without `protected_paths`, it means
  only that the tree's own commands exited 0.

### 2.6 Scoped agent keys (`grant`)

Problem: an agent key may record every agent type at any time it is valid.

- Time windows already exist: `valid-after` and `valid-before` in the key list. Because `time` is declared by the
  writer, an expiry is enforced only as far as the witness clock bounds it; the lower bound is open (2.12, N11).
- New public field `scopes` on protocol 2 owner `keys` entries: `{"<principal>": ["measured", "run", ...]}`. The
  types a principal may record are the intersection of its scope with its role's types. A scope stays in force
  until a later `keys` entry replaces it; a `keys` entry without `scopes` keeps the previous scopes.
- Scopes apply per principal (2.1); to scope one key, give it its own principal (`agent-<id>`).

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

### 2.12 Open items from the second adversarial review

The second review (2026-10-30) found the holes above, now closed, and the following of medium or low severity,
recorded with the proposed fix and left [OPEN] until implementation:

- N11 [OPEN] Backdating is bounded only by the last cosign: a witness SHOULD refuse an entry dated earlier than its
  clock minus the tolerance, unless a head containing it already carries a cosign from another listed witness
  within the tolerance.
- N12 [OPEN] A witness with a fast clock stalls the others: the time floor SHOULD be the earliest cosign time of the
  last quorum head, and writers date entries at the later of their clock and that floor.
- N15 [OPEN] For `resolves` and `corrects`, the device SHOULD fetch the referenced entry from the quorum chain,
  verify its private body against its `commitment`, and render that body.
- N16 [OPEN] `policy` SHOULD list the auditor principals whose alarms count for 2.5.
- N17 [OPEN] Runs SHOULD be triggered only by the gate, and condition 1 SHOULD require exit 0 from every run of the
  command on that tree, not the latest.
- N18 [OPEN] The required check SHOULD be strict (branch up to date) or run in a merge queue, and match runs on the
  tree the branch will point to.
- N19 [OPEN] An entry with no claims SHOULD be `self_reported`.
- N20 [OPEN] A run counts under the policy in force at the run; a verifier SHOULD also report a run whose runner was
  later removed.
- N21 [OPEN] A receipt checker derives `located_and_matched` and `attested` only after re-cutting the excerpt from a
  source file it hashed itself; otherwise `not_located`.
- N22 [OPEN] Salted attachment hashes (2.9) break the equality that 2.4 uses across entries; the policy difference
  needs the no-copy fallback that `keys` has; the character rule of 2.3 must also cover policy strings and URLs.
