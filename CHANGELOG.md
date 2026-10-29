# Changelog

All notable changes are listed here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

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
