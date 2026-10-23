#!/usr/bin/env python3
"""eilikrineia: a public commitment ledger between a person and the AI agents working for them.

Every statement an agent makes is committed by hash, chained to the previous entry, signed by its role key,
checked by code where it can be, read by an auditor from another vendor where it cannot, and anchored in time.
The owner signs the genesis and every change to the key list or to the auditor's code.

Only the Python standard library and ``ssh-keygen -Y`` are required to verify. The auditor never reads whole
files: evidence is a short excerpt cut by this program from an immutable copy, and every excerpt carries a proof
of where it came from.

Public (may live in an open repository): ``chain/``, ``keys/``, ``stamps/``, ``history/``, this file.
Private (never leaves the machine): ``private/`` (texts, salts, evidence vault, private keys, audit replies).

ponytail: one file on purpose, so that anyone can verify by downloading a single script.
"""

import argparse
import datetime
import gzip
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("EILIKRINEIA_ROOT", Path(__file__).resolve().parent))
GENESIS_PREV = "0" * 64
NAMESPACE = "eilikrineia"
ROLES = ("agent", "auditor", "owner")
TYPES = (
    "measured",  # claims checked by code (predicates), plus optional excerpts
    "assertion",  # what the agent tells the owner it did or found; always audited
    "opinion",  # hypothesis or recommendation; never judged as fact
    "correction",  # supersedes an earlier entry, which stays
    "run",  # a unit of work: inputs and outputs attached by hash
    "audit",  # auditor alarm (witness): an entry already seen changed or vanished
    "checkpoint",  # auditor: "verified through #N", carrying every verdict of that run
    "decision",  # owner only
    "genesis",  # owner only; first entry
    "keys",  # owner only; new key list
    "code",  # owner only; new pinned auditor code hash
)
OWNER_ONLY = ("decision", "genesis", "keys", "code")
AUDITOR_ONLY = ("audit", "checkpoint")
NEEDS_EVIDENCE = ("measured", "assertion", "run")
HASHED = (
    "seq", "time", "role", "type", "commitment", "attachments", "corrects", "audits", "prev",
    "signers_sha256", "code_sha256", "predecessor",
)  # fmt: skip
MAX_EXCERPT = 2000  # characters an auditor model ever sees per piece of evidence
SAMPLE_RATE = 0.25  # share of automated 'measured'/'run' entries sent to semantic audit


# ---------- hashing and layout ----------


def sha256_bytes(data):
    """Return the hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    """Return the hex SHA-256 of the file at ``path``, read in blocks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical(obj):
    """Serialize ``obj`` as canonical JSON bytes (sorted keys, no spaces)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def entry_hash(entry):
    """Hash the public fields of an entry (fields absent from the entry are skipped)."""
    return sha256_bytes(canonical({k: entry[k] for k in HASHED if k in entry}))


def now_utc():
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def layout(root=None):
    """Return the folder layout under ``root``.

    Parameters
    ----------
    root : path-like, optional
        Ledger root; defaults to ``EILIKRINEIA_ROOT`` or this file's folder.

    Returns
    -------
    dict
        Named paths for public and private folders.
    """
    r = Path(root or ROOT)
    p = r / "private"
    return {
        "root": r, "chain": r / "chain", "keys": r / "keys", "signers": r / "keys" / "allowed_signers",
        "stamps": r / "stamps", "private": p, "texts": p / "texts", "vault": p / "vault",
        "audits": p / "audits", "secret_keys": p / "keys",
    }  # fmt: skip


def entries(root=None):
    """Return all public entries in sequence order."""
    return [json.loads(f.read_text()) for f in sorted(layout(root)["chain"].glob("*.json"))]


# ---------- signatures ----------


def secret_key(role, root=None):
    """Locate the private key of ``role``; ``EILIKRINEIA_KEY_<ROLE>`` overrides the default path."""
    return Path(os.environ.get(f"EILIKRINEIA_KEY_{role.upper()}", layout(root)["secret_keys"] / role))


def sign(role, message, root=None):
    """Sign ``message`` with the role key (the owner's key asks for its passphrase)."""
    key = secret_key(role, root)
    if not key.exists():
        raise SystemExit(f"No private key for role '{role}' at {key}.")
    with tempfile.TemporaryDirectory() as d:
        msg = Path(d) / "m"
        msg.write_text(message)
        cmd = ["ssh-keygen", "-Y", "sign", "-q", "-f", str(key), "-n", NAMESPACE, str(msg)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("ssh-keygen sign failed: " + r.stderr.strip())
        return (Path(d) / "m.sig").read_text()


def signature_ok(role, message, signature, root=None, when=None):
    """Verify a signature against the keys valid for ``role`` at time ``when``."""
    with tempfile.TemporaryDirectory() as d:
        sig = Path(d) / "s.sig"
        sig.write_text(signature)
        signers = str(layout(root)["signers"])
        cmd = ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", role, "-n", NAMESPACE, "-s", str(sig)]
        if when:
            cmd += ["-O", "verify-time=" + re.sub(r"[-:T]", "", when)]
        return subprocess.run(cmd, input=message, capture_output=True, text=True).returncode == 0


# ---------- evidence: immutable copies, located excerpts ----------


def vault_put(path, root=None):
    """Store a gzip copy of a file in the content-addressed vault; the name is the SHA-256 of the ORIGINAL bytes."""
    digest = sha256_file(path)
    vault = layout(root)["vault"]
    target = vault / f"{digest}.gz"
    if not (target.exists() or (vault / digest).exists()):
        vault.mkdir(parents=True, exist_ok=True)
        with open(path, "rb") as src, gzip.GzipFile(target, "wb", mtime=0) as dst:  # mtime=0: same bytes every time
            shutil.copyfileobj(src, dst)
        os.chmod(target, 0o444)
    return digest


def vault_read(digest, root=None):
    """Return the original bytes of a vault copy (gzip, or a plain copy from before compression), or None."""
    vault = layout(root)["vault"]
    try:
        if (vault / f"{digest}.gz").exists():
            return gzip.decompress((vault / f"{digest}.gz").read_bytes())
        if (vault / digest).exists():
            return (vault / digest).read_bytes()
    except (OSError, EOFError, gzip.BadGzipFile):
        return b""  # unreadable copy: hashes to something else, so it is reported as altered
    return None


def compact(root=None):
    """Compress plain vault copies made before compression existed, after checking each one's hash."""
    vault, done = layout(root)["vault"], 0
    for f in sorted(vault.glob("*")):
        if f.suffix == ".gz" or len(f.name) != 64 or f.stat().st_uid != os.getuid() or sha256_file(f) != f.name:
            continue  # only copies this account owns (the auditor's own copies stay as they are)
        with open(f, "rb") as src, gzip.GzipFile(vault / f"{f.name}.gz", "wb", mtime=0) as dst:
            shutil.copyfileobj(src, dst)
        os.chmod(vault / f"{f.name}.gz", 0o444)
        f.chmod(0o644)
        f.unlink()
        done += 1
    return {"compressed": done}


def cut(text, locator):
    """Cut the excerpt selected by ``locator`` from ``text``.

    Parameters
    ----------
    text : str
        Full file content.
    locator : dict
        ``{"lines": [first, last]}`` (1-based, inclusive), ``{"json": "/pointer"}`` or ``{"all": true}``.

    Returns
    -------
    str
        The excerpt.
    """
    if "lines" in locator:
        first, last = locator["lines"]
        lines = text.splitlines()
        if not 1 <= first <= last <= len(lines):
            raise SystemExit(f"Line range {first}-{last} outside the file ({len(lines)} lines).")
        return "\n".join(lines[first - 1 : last])
    if "json" in locator:
        node = json.loads(text)
        for part in [p for p in locator["json"].split("/") if p]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        return json.dumps(node, ensure_ascii=False, sort_keys=True)
    if locator.get("all"):
        return text
    raise SystemExit(f"Unknown locator: {locator}")


def excerpt(digest, locator, root=None):
    """Re-cut an excerpt from the vault copy and return ``(text, sha256)``."""
    text = (vault_read(digest, root) or b"").decode(errors="replace")
    piece = cut(text, locator)
    return piece, sha256_bytes(piece.encode())


def parse_evidence(spec):
    """Parse ``FILE``, ``FILE:A-B`` (lines) or ``FILE#/json/pointer`` into ``(path, locator)``."""
    if "#/" in spec:
        path, pointer = spec.split("#", 1)
        return Path(path), {"json": pointer}
    m = re.fullmatch(r"(.+):(\d+)-(\d+)", spec)
    if m:
        return Path(m.group(1)), {"lines": [int(m.group(2)), int(m.group(3))]}
    return Path(spec), {"all": True}


# ---------- claims: what code can decide never reaches a model ----------


def check_claim(claim, root=None):
    """Decide a mechanical claim from its excerpt; return ``(passed, detail)``.

    Predicates
    ----------
    ``contains``: the excerpt contains ``args.text``.
    ``number``: ``args.pattern`` (one integer group) matches and equals ``args.value``.
    ``equals``: the excerpt (e.g. a JSON pointer value) equals ``args.value`` as JSON.
    ``semantic``: not decidable by code; goes to the auditor model.
    """
    ev = claim["evidence"]
    piece, digest = excerpt(ev["sha256"], ev["locator"], root)
    if digest != ev["excerpt_sha256"]:
        return False, "excerpt changed since recording"
    pred, args = claim["predicate"], claim.get("args", {})
    if pred == "contains":
        return args["text"] in piece, f"contains {args['text']!r}"
    if pred == "number":
        m = re.search(args["pattern"], piece)
        found = int(m.group(1)) if m else None
        return found == int(args["value"]), f"{args['pattern']} -> {found}, expected {args['value']}"
    if pred == "equals":
        return json.loads(piece) == args["value"], f"equals {args['value']!r}"
    return None, "semantic"


def build_claim(spec, root=None):
    """Turn ``{"predicate", "args", "evidence": "FILE[:A-B|#/ptr]"}`` into a stored claim with proof."""
    path, locator = parse_evidence(spec["evidence"])
    if not path.is_file():
        raise SystemExit(f"Evidence is not a file: {path}")
    digest = vault_put(path, root)
    piece, piece_sha = excerpt(digest, locator, root)
    if len(piece) > MAX_EXCERPT:
        raise SystemExit(f"Excerpt of {path.name} has {len(piece)} characters (max {MAX_EXCERPT}); narrow the locator.")
    return {
        "predicate": spec["predicate"],
        "args": spec.get("args", {}),
        "evidence": {"file": path.name, "sha256": digest, "locator": locator, "excerpt_sha256": piece_sha},
    }


# ---------- recording ----------


def committed_keys(chain):
    """Return the key-list hash last signed by the owner (genesis or 'keys')."""
    return next((e["signers_sha256"] for e in reversed(chain) if "signers_sha256" in e), None)


def committed_code(chain):
    """Return the auditor code hash last signed by the owner (genesis or 'code')."""
    return next((e["code_sha256"] for e in reversed(chain) if "code_sha256" in e), None)


def record(role, kind, text, *, claims=(), attachments=(), corrects=None, audits=None, root=None, when=None,
           predecessor=None):  # fmt: skip
    """Append one signed entry.

    Parameters
    ----------
    role : {'agent', 'auditor', 'owner'}
        Who signs.
    kind : str
        One of ``TYPES``.
    text : str
        The statement, kept private; only its salted hash is public.
    claims : sequence of dict
        Claim specs, see ``build_claim``.
    attachments : sequence of path-like
        Files committed by hash only (any size; never sent to a model).
    corrects, audits : str, optional
        Hash of the entry this one corrects or audits.
    root : path-like, optional
        Ledger root.
    when : str, optional
        Timestamp override (tests).
    predecessor : dict, optional
        Head of the previous ledger, for a genesis that takes it over.

    Returns
    -------
    dict
        ``{"seq", "hash"}`` of the new entry.
    """
    if role not in ROLES or kind not in TYPES or not text.strip():
        raise SystemExit("Invalid role, type or empty text.")
    if kind in OWNER_ONLY and role != "owner":
        raise SystemExit(f"Type '{kind}' is owner-only.")
    if kind in AUDITOR_ONLY and role != "auditor":
        raise SystemExit(f"Type '{kind}' is auditor-only.")
    if kind in NEEDS_EVIDENCE and not (claims or attachments):
        raise SystemExit(f"Type '{kind}' needs evidence; without it, record an 'opinion'.")
    lay = layout(root)
    chain = entries(root)
    if kind == "genesis" and chain:
        raise SystemExit("Genesis only on an empty chain.")
    if not chain and kind != "genesis":
        raise SystemExit("The chain must start with the owner's genesis.")
    if chain and kind != "keys" and committed_keys(chain) != sha256_file(lay["signers"]):
        raise SystemExit("The key list changed after the owner's last signature; the owner must record 'keys'.")
    known = {e["hash"] for e in chain}
    for ref in (corrects, audits):
        if ref and ref not in known:
            raise SystemExit(f"Referenced hash not in the chain: {ref}")
    if kind == "correction" and not corrects:
        raise SystemExit("A correction needs --corrects <hash>.")
    if kind == "audit" and not audits:
        raise SystemExit("An audit needs --audits <hash>.")
    stored_claims = [build_claim(c, root) for c in claims]
    attached = []
    for path in attachments:
        path = Path(path)
        if not path.is_file():
            raise SystemExit(f"Attachment is not a file: {path}")
        attached.append({"file": str(path.resolve()), "sha256": vault_put(path, root)})
    salt = secrets.token_hex(32)
    private = {"text": text, "claims": stored_claims, "attachments": attached}
    entry = {
        "seq": len(chain) + 1, "time": when or now_utc(), "role": role, "type": kind,
        "commitment": sha256_bytes(bytes.fromhex(salt) + canonical(private)),
        "attachments": sorted({a["sha256"] for a in attached} | {c["evidence"]["sha256"] for c in stored_claims}),
        "prev": chain[-1]["hash"] if chain else GENESIS_PREV,
    }  # fmt: skip
    if corrects:
        entry["corrects"] = corrects
    if audits:
        entry["audits"] = audits
    if kind in ("genesis", "keys"):
        entry["signers_sha256"] = sha256_file(lay["signers"])
    if kind in ("genesis", "code"):
        entry["code_sha256"] = sha256_file(lay["root"] / "eilikrineia.py")
    if kind == "genesis" and predecessor:
        entry["predecessor"] = predecessor
    entry["hash"] = entry_hash(entry)
    entry["signature"] = sign(role, entry["hash"], root)
    for folder in (lay["texts"], lay["chain"]):
        folder.mkdir(parents=True, exist_ok=True)
    (lay["texts"] / f"{entry['seq']:06d}.json").write_text(
        json.dumps({"seq": entry["seq"], "hash": entry["hash"], "salt": salt, **private}, ensure_ascii=False, indent=1)
    )
    (lay["chain"] / f"{entry['seq']:06d}.json").write_text(json.dumps(entry, ensure_ascii=False, indent=1))
    return {"seq": entry["seq"], "hash": entry["hash"]}


# ---------- verification ----------


def verify(root=None, private=False, since=0):
    """Verify the chain.

    Parameters
    ----------
    root : path-like, optional
        Ledger root.
    private : bool
        Also check texts against commitments and every claim against its vault excerpt.
    since : int
        Skip signature and private checks for entries ``<= since`` (incremental mode); linkage is always checked.

    Returns
    -------
    dict
        ``ok``, ``entries``, ``head``, ``problems``, ``trust_root``.
    """
    problems, prev, seen = [], GENESIS_PREV, set()
    chain = entries(root)
    lay = layout(root)
    if chain:
        first = chain[0]
        if first.get("type") != "genesis" or first.get("role") != "owner":
            problems.append("#1: the chain does not start with the owner's genesis")
        if committed_keys(chain) != sha256_file(lay["signers"]):
            problems.append("keys/allowed_signers differs from the list last signed by the owner")
    for i, e in enumerate(chain, 1):
        s = e.get("seq")
        if s != i:
            problems.append(f"#{s}: sequence broken (expected {i})")
        if e.get("prev") != prev:
            problems.append(f"#{s}: 'prev' is not the previous entry's hash")
        if entry_hash(e) != e.get("hash"):
            problems.append(f"#{s}: hash does not match content (entry altered)")
        if i > 1 and e.get("time", "") < chain[i - 2].get("time", ""):
            problems.append(f"#{s}: time earlier than the previous entry (backdated)")
        for ref in ("corrects", "audits"):
            if e.get(ref) and e[ref] not in seen:
                problems.append(f"#{s}: '{ref}' points to a hash not earlier in the chain")
        if e.get("type") in OWNER_ONLY and e.get("role") != "owner":
            problems.append(f"#{s}: owner-only type signed by '{e.get('role')}'")
        if e.get("type") in AUDITOR_ONLY and e.get("role") != "auditor":
            problems.append(f"#{s}: auditor-only type signed by '{e.get('role')}'")
        if s > since:
            if not signature_ok(e.get("role", ""), e.get("hash", ""), e.get("signature", ""), root, e.get("time")):
                problems.append(f"#{s}: invalid signature for role '{e.get('role')}' at the entry's time")
            if private:
                problems += _verify_private(e, root)
        seen.add(e.get("hash"))
        prev = e.get("hash")
    return {
        "ok": not problems, "entries": len(chain), "head": prev, "problems": problems,
        "trust_root": "owner genesis" if chain and chain[0].get("role") == "owner" else "none",
    }  # fmt: skip


def _verify_private(e, root):
    """Check one entry's private text and claims against its public commitment."""
    path = layout(root)["texts"] / f"{e['seq']:06d}.json"
    if not path.exists():
        return [f"#{e['seq']}: private text missing"]
    d = json.loads(path.read_text())
    body = {k: d[k] for k in ("text", "claims", "attachments")}
    out = []
    if sha256_bytes(bytes.fromhex(d["salt"]) + canonical(body)) != e["commitment"]:
        out.append(f"#{e['seq']}: private text does not match the public commitment")
    for item in [c["evidence"] for c in d["claims"]] + d["attachments"]:
        data = vault_read(item["sha256"], root)
        if data is None:
            out.append(f"#{e['seq']}: missing from the vault: {item['file']}")
        elif sha256_bytes(data) != item["sha256"]:  # the vault copy is the proof; it must hash to its own name
            out.append(f"#{e['seq']}: vault copy altered: {item['file']}")
        elif "locator" in item and excerpt(item["sha256"], item["locator"], root)[1] != item["excerpt_sha256"]:
            out.append(f"#{e['seq']}: excerpt no longer matches: {item['file']}")
    return out


def last_checkpoint(chain):
    """Return the sequence number verified by the auditor's last checkpoint (0 if none)."""
    for e in reversed(chain):
        if e.get("type") == "checkpoint":
            return e["seq"] - 1
    return 0


# ---------- audit ----------

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
}
AUDIT_PROMPT = (
    "You are an independent auditor. Judge ONLY with the material below, without outside knowledge or goodwill. "
    "An AI agent recorded a STATEMENT and attached EXCERPTS cut by a program from immutable copies of files. "
    "Answer whether the excerpts support the statement: 'supported' (everything it says is in the excerpts), "
    "'partial' (part is, part is not, or it overreaches), 'unsupported'. Mechanical checks were already decided "
    "by code and are listed for context. Quote the exact point in the reason. Reply in the statement's language."
    "\n\n=== STATEMENT ({kind}) ===\n{text}\n\n=== MECHANICAL CHECKS ===\n{mech}\n\n=== EXCERPTS ===\n{ev}\n"
)


def call_auditor(prompt, auditor="grok"):
    """Ask a model from another vendor, through that vendor's own subscription CLI (no pay-per-use API)."""
    with tempfile.TemporaryDirectory() as d:  # empty cwd: the grok CLI writes files where it runs
        f = Path(d) / "prompt.txt"
        f.write_text(prompt)
        if auditor == "grok":
            exe = shutil.which("grok") or str(Path.home() / ".grok/bin/grok")
            cmd = [exe, "--prompt-file", str(f), "--json-schema", json.dumps(VERDICT_SCHEMA),
                   "--disable-web-search", "--no-subagents", "--no-plan", "--cwd", d]  # fmt: skip
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=d)
            raw = r.stdout
        elif auditor == "codex":
            out = Path(d) / "out.txt"
            cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-C", d,
                   "--output-last-message", str(out), "-"]  # fmt: skip
            r = subprocess.run(cmd, input=prompt + '\nReply ONLY with JSON {"verdict":..,"reason":..}.',
                               capture_output=True, text=True, timeout=1200, cwd=d)  # fmt: skip
            raw = out.read_text() if out.exists() else r.stdout
        else:
            raise SystemExit(f"Unknown auditor: {auditor}")
        if r.returncode:
            raise SystemExit(f"Auditor {auditor} exited {r.returncode}: {r.stderr[-400:]}")
    return raw


def parse_verdict(raw):
    """Extract ``{"verdict", "reason"}`` from a raw reply (plain JSON, an envelope, or embedded)."""
    candidates = [raw]
    try:
        env = json.loads(raw)
        if isinstance(env, dict):
            for k in ("structured_output", "text", "result", "output"):
                if k in env:
                    candidates.insert(0, env[k] if isinstance(env[k], str) else json.dumps(env[k]))
            candidates.insert(0, json.dumps(env))
    except json.JSONDecodeError:
        pass
    allowed = VERDICT_SCHEMA["properties"]["verdict"]["enum"]
    for c in candidates:
        i, j = c.find("{"), c.rfind("}")
        while i != -1 and j > i:
            try:
                v = json.loads(c[i : j + 1])
                if isinstance(v, dict) and v.get("verdict") in allowed:
                    return {"verdict": v["verdict"], "reason": str(v.get("reason", ""))}
                break
            except json.JSONDecodeError:
                j = c.rfind("}", 0, j)
    raise SystemExit("Auditor reply without a valid verdict.")


def sampled(entry, head):
    """Decide whether an automated entry goes to semantic audit, seeded by a later head the writer could not know."""
    seed = int(sha256_bytes((head + entry["hash"]).encode())[:8], 16)
    return seed / 0xFFFFFFFF < SAMPLE_RATE


def audit(root=None, auditor="grok", ask=call_auditor):
    """Audit every entry recorded since the last checkpoint and sign ONE checkpoint that carries all verdicts.

    Mechanical claims are decided by code. The model reads only excerpts (never whole files), and only for
    assertions and corrections (always) and a sample of measured/run entries. Opinions are never judged. Nothing
    new since the last checkpoint means no entry at all: an idle ledger does not grow.
    """
    lay = layout(root)
    chain = entries(root)
    since = last_checkpoint(chain)
    new = [e for e in chain[since:] if e["role"] != "auditor"]
    if not new:
        return {"audited": [], "checkpoint": None}
    v = verify(root, private=True, since=since)
    if not v["ok"]:
        raise SystemExit("Verification failed; nothing audited: " + "; ".join(v["problems"]))
    head, results = chain[-1]["hash"], []
    for e in new:
        # opinions are never judged; owner entries are decisions, checked by code (signature, pinned hashes)
        if e["type"] in OWNER_ONLY or e["type"] == "opinion":
            continue
        d = json.loads((lay["texts"] / f"{e['seq']:06d}.json").read_text())
        mech, pieces = [], []
        for c in d["claims"]:
            passed, detail = check_claim(c, root)
            piece = excerpt(c["evidence"]["sha256"], c["evidence"]["locator"], root)[0]
            pieces.append(f"--- {c['evidence']['file']} {c['evidence']['locator']} ---\n{piece}")
            if passed is not None:
                mech.append({"predicate": c["predicate"], "passed": passed, "detail": detail})
        result = {"seq": e["seq"], "hash": e["hash"], "mechanical": mech}
        if e["type"] in ("assertion", "correction") or sampled(e, head):
            prompt = AUDIT_PROMPT.format(
                kind=e["type"], text=d["text"],
                mech=json.dumps(mech, ensure_ascii=False) or "none",
                ev="\n\n".join(pieces) or "(no excerpts; attachments committed by hash only)",
            )  # fmt: skip
            result.update(parse_verdict(ask(prompt, auditor)), auditor=auditor)
        else:
            result["semantic"] = "not sampled"
        if any(not m["passed"] for m in mech):
            result["verdict"] = "unsupported"
        results.append(result)
    through = chain[-1]["seq"]
    reply = lay["audits"] / f"through-{through:06d}-{auditor}.json"
    reply.parent.mkdir(parents=True, exist_ok=True)
    reply.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    summary = {
        "through": through,
        "results": [
            {k: r[k] for k in ("seq", "hash") if k in r} | {"verdict": r.get("verdict", "mechanical only")}
            for r in results
        ],
    }
    cp = record("auditor", "checkpoint", json.dumps(summary, ensure_ascii=False), attachments=[reply], root=root)
    return {"audited": summary["results"], "checkpoint": cp["seq"]}


# ---------- witness: no silent rewrite of the unpublished tail ----------


def witness(root=None, ledger=None):
    """Keep, in a file only the auditor's account can write, the hash of every entry already seen.

    If an entry already seen changed or vanished, record an alarm as an audit signed by the auditor.
    The scheduler runs this on every change to ``chain/``, so the window is seconds, not hours.
    """
    path = Path(ledger or os.environ.get("EILIKRINEIA_WITNESS", ""))
    if str(path) in ("", "."):
        raise SystemExit("Set the witness file (EILIKRINEIA_WITNESS).")
    data = json.loads(path.read_text()) if path.exists() else {"seen": [], "alarms": []}
    chain = entries(root)
    current = {e["seq"]: e["hash"] for e in chain}
    diverged = [w for w in data["seen"] if current.get(w["seq"]) != w["hash"]]
    known = {(w["seq"], w["hash"]) for w in data["seen"]}
    new = [
        {"seq": e["seq"], "hash": e["hash"], "seen_at": now_utc()} for e in chain if (e["seq"], e["hash"]) not in known
    ]
    data["seen"] += new
    alarm = None
    if diverged:
        report = {"at": now_utc(), "seen_before": diverged,
                  "now": [{"seq": w["seq"], "hash": current.get(w["seq"])} for w in diverged]}  # fmt: skip
        data["alarms"].append(report)
        f = layout(root)["audits"] / f"alarm-{report['at'].replace(':', '')}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(report, indent=1))
        text = json.dumps({"verdict": "unsupported", "reason": f"ALARM: {len(diverged)} witnessed entries changed"})
        alarm = record("auditor", "audit", text, attachments=[f], audits=chain[-1]["hash"], root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))
    return {"newly_witnessed": len(new), "diverged": diverged, "alarm": alarm}


# ---------- owner operations ----------


def init(root=None, roles=("agent", "auditor")):
    """Create missing role keys and append them to the key list; never rewrite or recreate a published key."""
    lay = layout(root)
    first_time = not lay["private"].exists()
    for k in ("chain", "keys", "secret_keys", "texts", "vault", "audits"):
        lay[k].mkdir(parents=True, exist_ok=True)
    if first_time:
        os.chmod(lay["private"], 0o700)
        os.chmod(lay["secret_keys"], 0o700)
    existing = lay["signers"].read_text().splitlines() if lay["signers"].exists() else []
    published = {line.split()[0] for line in existing if line.strip()}
    added = []
    for role in ROLES:
        key = lay["secret_keys"] / role
        if role in published or (role not in roles and not key.exists()):
            continue
        if not key.exists():
            cmd = ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"{NAMESPACE}-{role}", "-f", str(key)]
            subprocess.run(cmd, check=True, capture_output=True)
        kind, body = (lay["secret_keys"] / f"{role}.pub").read_text().split()[:2]
        added.append(f'{role} namespaces="{NAMESPACE}" {kind} {body}')
    if added:
        lay["signers"].write_text("\n".join(existing + added) + "\n")
    return {"signers": str(lay["signers"]), "added": [a.split()[0] for a in added]}


def rotate(role, new_public, root=None, when=None):
    """Retire the current key of ``role`` (valid-before=now) and publish the new one (valid-after=now)."""
    when = when or datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%SZ")
    signers = layout(root)["signers"]
    lines = []
    for line in signers.read_text().splitlines():
        name, opts, rest = line.split(" ", 2)
        if name == role and "valid-before" not in opts:
            opts += f',valid-before="{when}"'
        lines.append(" ".join([name, opts, rest]))
    kind, body = Path(new_public).read_text().split()[:2]
    lines.append(f'{role} namespaces="{NAMESPACE}",valid-after="{when}" {kind} {body}')
    signers.write_text("\n".join(lines) + "\n")
    return {"role": role, "rotated_at": when}


def genesis(root=None, text=None, predecessor=None):
    """Start the chain with the owner's signature; it pins the key list and the auditor code."""
    text = text or (
        "Owner genesis. I start this ledger with my key. The keys in the committed list are valid; any change "
        "needs a 'keys' entry signed by me. The auditor runs only the code whose hash I sign here or in a later "
        "'code' entry."
    )
    if predecessor:
        text += f" I take over the previous ledger {predecessor['version']} ({predecessor['entries']} entries, head "
        text += f"{predecessor['head']}), kept in history/."
    init(root)
    return record("owner", "genesis", text, root=root, predecessor=predecessor,
                  attachments=[layout(root)["signers"], layout(root)["root"] / "eilikrineia.py"])  # fmt: skip


def pinned_ok(code_path, root=None):
    """Return True when ``code_path`` has the hash the owner last signed; the auditor refuses to run otherwise."""
    return sha256_file(code_path) == committed_code(entries(root))


# ---------- timestamping and publishing ----------

PUBLIC = (
    "README.md", "PROTOCOL.md", "CHANGELOG.md", "LICENSE", "LICENSES", "NOTICE", "CITATION.cff",
    "codemeta.json", ".zenodo.json", "pyproject.toml", "eilikrineia.py", "tests", "scripts", ".github",
    ".gitignore", "chain", "keys", "stamps", "history",
)  # fmt: skip
FORBIDDEN = ("PRIVATE KEY", "BEGIN OPENSSH")


def _ots(root):
    local = layout(root)["root"] / ".venv" / "bin" / "ots"
    return str(local) if local.exists() else (shutil.which("ots") or "")


def stamp(root=None):
    """Timestamp the current head with OpenTimestamps (only the hash leaves) and upgrade pending stamps."""
    lay = layout(root)
    chain = entries(root)
    if not chain:
        return {"stamp": None}
    ots = _ots(root)
    if not ots:
        raise SystemExit("OpenTimestamps client missing (pip install opentimestamps-client).")
    lay["stamps"].mkdir(exist_ok=True)
    head = chain[-1]
    target = lay["stamps"] / f"{head['seq']:06d}.txt"
    if not target.exists():
        target.write_text(f"eilikrineia\nseq {head['seq']}\nhead {head['hash']}\n")
        r = subprocess.run([ots, "stamp", str(target)], capture_output=True, text=True, timeout=300)
        if r.returncode:
            raise SystemExit("ots stamp failed: " + r.stderr[-400:])
    upgraded = []
    for proof in sorted(lay["stamps"].glob("*.ots")):
        u = subprocess.run([ots, "upgrade", str(proof)], capture_output=True, text=True, timeout=300)
        if u.returncode == 0 and "Success" in u.stdout + u.stderr:
            upgraded.append(proof.name)
    return {"stamp": target.name + ".ots", "seq": head["seq"], "upgraded": upgraded}


def publish(root=None, push=True):
    """Verify, timestamp, check that nothing private leaves, commit and push everything not yet on the remote."""
    lay = layout(root)
    v = verify(root, private=True)
    if not v["ok"]:
        raise SystemExit("Verification failed; nothing published: " + "; ".join(v["problems"]))
    st = stamp(root)
    git = ["git", "-C", str(lay["root"])]
    present = [p for p in PUBLIC if (lay["root"] / p).exists()]
    subprocess.run(git + ["add", "-A", "--", *present], check=True)
    staged = subprocess.run(git + ["diff", "--cached", "--name-only"], capture_output=True, text=True).stdout.split()
    if staged:
        title = f"chain: through #{v['entries']}, head {v['head'][:12]}"
        subprocess.run(git + ["commit", "-q", "-m", title], check=True)
    env = dict(os.environ, DOCTRINE_PUSH_OK="1")  # owner's exception no. 3: this repo, this command only
    key = secret_key("deploy", root)
    if key.exists():  # deploy key: write access to this repository only
        env["GIT_SSH_COMMAND"] = f"ssh -i {key} -o IdentitiesOnly=yes"
    subprocess.run(git + ["fetch", "-q", "origin"], env=env, capture_output=True)
    ahead = subprocess.run(git + ["diff", "--name-only", "--diff-filter=AM", "origin/main..HEAD"],
                           capture_output=True, text=True).stdout.split()  # fmt: skip
    tracked = subprocess.run(git + ["ls-files"], capture_output=True, text=True).stdout.split()
    bad = [n for n in tracked if n.startswith("private/") or "/private/" in n or not n.startswith(PUBLIC)]
    for n in ahead:
        f = lay["root"] / n
        exempt = n in ("eilikrineia.py", "tests/test_eilikrineia.py") or re.fullmatch(r"history/[^/]+\.py", n)
        if f.is_file() and not exempt:  # code that names the forbidden markers is not a leak
            if any(x in f.read_text(errors="replace") for x in FORBIDDEN):
                bad.append(n)
    gitleaks = shutil.which("gitleaks")
    if gitleaks and ahead:
        with tempfile.TemporaryDirectory() as d:
            for n in ahead:
                if (lay["root"] / n).is_file():
                    (Path(d) / n).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(lay["root"] / n, Path(d) / n)
            g = subprocess.run([gitleaks, "dir", d, "--no-banner", "--redact", "--exit-code", "1"],
                               capture_output=True, text=True)  # fmt: skip
            if g.returncode:
                bad.append("gitleaks: " + (g.stdout + g.stderr)[-300:])
    if bad:
        raise SystemExit(f"Refusing to publish: {sorted(set(bad))}")
    pushed = False
    if push and subprocess.run(git + ["rev-list", "--count", "origin/main..HEAD"], capture_output=True,
                               text=True).stdout.strip() not in ("", "0"):  # fmt: skip
        p = subprocess.run(git + ["push", "-q", "origin", "HEAD:main"], capture_output=True, text=True, env=env)
        if p.returncode:
            raise SystemExit("push failed: " + p.stderr[-400:])
        pushed = True
    return {"entries": v["entries"], "head": v["head"], "pushed": pushed, "files": ahead,
            "gitleaks": "ran" if gitleaks else "MISSING", **st}  # fmt: skip


def reveal(seq, root=None):
    """Return the private text and salt of one entry, for the owner to publish if he decides to."""
    d = json.loads((layout(root)["texts"] / f"{int(seq):06d}.json").read_text())
    return {"seq": d["seq"], "hash": d["hash"], "salt": d["salt"], "text": d["text"]}


# ---------- command line ----------


def main(argv=None):
    """Run the command-line interface."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    r = sub.add_parser("record")
    r.add_argument("--role", required=True, choices=ROLES)
    r.add_argument("--type", required=True, choices=TYPES, dest="kind")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--text-file", type=Path)
    r.add_argument("--claims", type=Path, help="JSON list of {predicate, args, evidence: FILE[:A-B|#/ptr]}")
    r.add_argument("--evidence", action="append", default=[], help="FILE[:A-B|#/ptr]: excerpt for semantic audit")
    r.add_argument("--attach", action="append", default=[], help="file committed by hash only")
    r.add_argument("--corrects")
    v = sub.add_parser("verify")
    v.add_argument("--private", action="store_true")
    sub.add_parser("audit").add_argument("--auditor", default="grok", choices=["grok", "codex"])
    sub.add_parser("witness").add_argument("--file", type=Path)
    gn = sub.add_parser("genesis")
    gn.add_argument("--text")
    gn.add_argument("--predecessor", type=Path, help="JSON {version, entries, head} of the ledger taken over")
    rt = sub.add_parser("rotate")
    rt.add_argument("role", choices=ROLES)
    rt.add_argument("new_public", type=Path)
    pc = sub.add_parser("pinned-ok")
    pc.add_argument("code", type=Path)
    sub.add_parser("compact")
    sub.add_parser("stamp")
    sub.add_parser("publish").add_argument("--no-push", action="store_true")
    sub.add_parser("reveal").add_argument("seq", type=int)
    a = ap.parse_args(argv)
    if a.cmd == "init":
        out = init(a.root)
    elif a.cmd == "record":
        text = a.text if a.text is not None else a.text_file.read_text()
        claims = json.loads(a.claims.read_text()) if a.claims else []
        claims += [{"predicate": "semantic", "evidence": spec} for spec in a.evidence]
        out = record(a.role, a.kind, text, claims=claims, attachments=a.attach, corrects=a.corrects, root=a.root)
    elif a.cmd == "verify":
        out = verify(a.root, a.private)
    elif a.cmd == "audit":
        out = audit(a.root, a.auditor)
    elif a.cmd == "witness":
        out = witness(a.root, a.file)
    elif a.cmd == "genesis":
        pred = json.loads(a.predecessor.read_text()) if a.predecessor else None
        out = genesis(a.root, a.text, pred)
    elif a.cmd == "rotate":
        out = rotate(a.role, a.new_public, a.root)
    elif a.cmd == "pinned-ok":
        out = {"ok": pinned_ok(a.code, a.root)}
    elif a.cmd == "compact":
        out = compact(a.root)
    elif a.cmd == "stamp":
        out = stamp(a.root)
    elif a.cmd == "publish":
        out = publish(a.root, push=not a.no_push)
    else:
        out = reveal(a.seq, a.root)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not isinstance(out, dict) or out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
