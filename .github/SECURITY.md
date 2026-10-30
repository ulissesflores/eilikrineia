# Security policy

## Supported versions

Only the latest release receives fixes. Version 1.0.0 is affected by the advisory below; version 1.0.1 fixes it.

## Advisory: trust root in 1.0.0 (fixed in 1.0.1)

- **Affected:** `verify`, `pinned-ok` and the auditor job (`scripts/auditor-run.sh`) of version 1.0.0.
- **Defect:** the pinned key list and the pinned auditor code were taken from the last entry carrying
  `signers_sha256` or `code_sha256`, whatever its role, type or signature. A raw unsigned file in `chain/` made
  `pinned-ok` accept arbitrary code, which the auditor job then adopted; an agent-signed entry could commit a key
  list with a planted owner key. The verifier also accepted unknown types and fields outside the hash.
- **Exploited:** no. Reproduced in a scratch ledger; this repository's ledger carries the owner-only fields only on
  owner entries #1, #10 and #64 (ledger entries #70 and #75).
- **Action:** upgrade to 1.0.1; do not use the 1.0.0 verifier or auditor job. Details in [`CHANGELOG.md`](../CHANGELOG.md) under 1.0.1.

## Scope of the guarantees

The tool's guarantees hold only while the agent cannot reach the owner's private key or passphrase, the auditor's
OS account, or the witness file. An agent that can become root on the machine defeats them; that is a documented
limit, not a vulnerability. See "Trust boundary of protocol 1" in [`PROTOCOL.md`](../PROTOCOL.md).

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: the **Security** tab of this repository, then **Report a
vulnerability**. Do not open a public issue for an unfixed vulnerability.
