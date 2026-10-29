# Changelog

All notable changes are listed here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [1.0.1] — 2026-10-29

### Security
- The pinned key list and the pinned auditor code now count only entries the owner really signed. In 1.0.0 the
  last entry carrying `signers_sha256` or `code_sha256` counted whatever its role, type or signature: a raw
  unsigned file in `chain/` made `pinned-ok` accept any code (and the auditor job adopts code before it verifies),
  and an agent-signed entry could commit a key list with a planted owner key. Found by an adversarial review of
  `PROTOCOL.md`, reproduced in a scratch ledger, never used in this repository's ledger (entry #75).
- Every entry is checked against the key list in force when it was written, kept in `keys/` as
  `allowed_signers.<sha256>` whenever the owner signs one; the current file is never trusted by itself. An owner
  key is therefore replaced by a `keys` entry signed with the OLD owner key.
- `verify` fails closed on an unknown type, an unknown role, a field outside the hash, and an owner-only field
  (`signers_sha256`, `code_sha256`, `predecessor`) on any other entry.
- `pinned-ok` anchors the trust root outside the folders the agent can write: the whole chain must be well linked
  and every entry the witness (in the auditor's account) has seen must be unchanged, so a forged genesis or a cut
  tail cannot bring back older or foreign code (second adversarial review, entry #77). Entries that go back in
  time or are not JSON objects end the trusted prefix; malformed signatures no longer crash the check; the key
  list is hashed and handed to `ssh-keygen` from the same bytes.
- `scripts/auditor-run.sh` runs the witness before deciding to adopt new code. It is installed as root in the
  auditor's account: re-run `scripts/install-auditor-macos.sh` with `sudo` after signing this release's code.

### Added
- `PROTOCOL.md`: normative wire format and verification of protocol 1, as implemented, and the protocol 2 draft
  (versioning with fail-closed verification, witness quorum, scoped agent keys, memory seals, tool calls,
  receipts). Nothing of protocol 2 is implemented.

## [1.0.0] — 2026-10-29

### Fixed
- `publish` stops when `git fetch` fails: the leak checks compared against a stale `origin/main` (was: fetch
  result ignored).
- `rotate` reads the key list in the ssh-keygen ALLOWED SIGNERS format: lines without options are retired
  correctly (was: `valid-before` glued to the key type), blank lines and comments pass through, and an unreadable
  line stops the rotation before anything is written.

### Added
- README examples for `witness` and `audit`, with the deployment rule the code cannot enforce: the witness file
  must be writable by the auditor's account only.

## [0.3.0] — 2026-10-23

### Changed
- One checkpoint per auditor run carries every verdict of that run (was one audit entry per audited entry).
- An idle ledger adds nothing: no checkpoint when nothing new was recorded (was one per scheduled run).
- The evidence vault stores gzip copies named by the hash of the original bytes; `compact` converts older copies.

## [0.2.0] — 2026-10-23

### Changed
- Restarted the ledger in English under a new owner genesis that takes over the previous one; v0 and v1 moved
  to `history/` with a frozen copy of the v1 script to verify them.
- Typed claims: what code can decide (number, contains, equals) never reaches a model.
- The auditor model reads only excerpts (at most 2,000 characters each) cut by the program from immutable
  vault copies, each with a proof of position and hash; whole files are attached by hash only.
- Semantic audit: every assertion and correction; a sample of measured and run entries, seeded by a later head.
- Incremental audit through auditor-signed checkpoints.
- The auditor runs a pinned copy of the code that changes only to an owner-signed hash.

## [0.1.0] — 2026-10-23

### Added
- First ledger (Portuguese): hash chain, role signatures, auditor from another vendor, OpenTimestamps,
  owner genesis (v1), auditor in a separate macOS account, witness against silent rewriting.
