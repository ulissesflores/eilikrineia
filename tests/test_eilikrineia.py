"""Tests for every guarantee the README states. Standard library only (unittest)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import eilikrineia as ek  # noqa: E402

OWNER_PASSPHRASE = "only-the-owner-knows"
LONG = "\n".join(f"line {i}: filler text that an auditor model should never have to read" for i in range(1, 400))


def keygen(path, passphrase=""):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", passphrase, "-f", str(path)], check=True)


class Ledger(unittest.TestCase):
    """A fresh ledger with agent and auditor keys and a passphrase-protected owner key, already in genesis."""

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.root = Path(self._d.name) / "ledger"
        self.root.mkdir()
        shutil.copy(Path(ek.__file__), self.root / "eilikrineia.py")
        ek.init(self.root)
        keygen(self.root / "private" / "keys" / "owner", OWNER_PASSPHRASE)
        askpass = Path(self._d.name) / "askpass.sh"  # stands in for the owner typing the passphrase
        askpass.write_text(f"#!/bin/sh\necho {OWNER_PASSPHRASE}\n")
        askpass.chmod(0o755)
        self._env = {k: os.environ.get(k) for k in ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "DISPLAY")}
        os.environ.update(SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE="force", DISPLAY=":0")
        ek.genesis(self.root)
        self.log = Path(self._d.name) / "test-output.txt"
        self.log.write_text("collecting...\nRan 25 tests in 1.2s\n\nOK\n" + LONG)

    def tearDown(self):
        for k, v in self._env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self._d.cleanup()

    def measured(self, value=25, lines="2-4"):
        claim = {"predicate": "number", "args": {"pattern": r"Ran (\d+) tests", "value": value},
                 "evidence": f"{self.log}:{lines}"}  # fmt: skip
        return ek.record("agent", "measured", f"The suite ran {value} tests.", claims=[claim], root=self.root)


class GenesisAndKeys(Ledger):
    def test_chain_starts_with_owner_genesis(self):
        first = ek.entries(self.root)[0]
        self.assertEqual((first["type"], first["role"]), ("genesis", "owner"))
        v = ek.verify(self.root, private=True)
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["trust_root"], "owner genesis")

    def test_agent_cannot_sign_owner_types(self):
        for kind in ("genesis", "keys", "code", "decision"):
            with self.assertRaises(SystemExit):
                ek.record("agent", kind, "forged", root=self.root)

    def test_key_list_change_without_owner_is_rejected(self):
        keygen(self.root / "intruder")
        pub = (self.root / "intruder.pub").read_text().split()
        signers = self.root / "keys" / "allowed_signers"
        signers.write_text(signers.read_text() + f'owner namespaces="eilikrineia" {pub[0]} {pub[1]}\n')
        self.assertIn("differs from the list last signed", " ".join(ek.verify(self.root)["problems"]))
        with self.assertRaises(SystemExit):
            self.measured()

    def test_rotation_signed_by_owner_retires_the_old_key(self):
        keygen(self.root / "new_agent")
        ek.rotate("agent", self.root / "new_agent.pub", self.root, when="20990101000000Z")
        ek.record("owner", "keys", "New agent key.", root=self.root, when="2099-01-01T00:00:01Z")
        # the old agent key, after its retirement, is not accepted
        ek.record("agent", "opinion", "signed with a retired key", root=self.root, when="2099-01-02T00:00:00Z")
        self.assertIn("#3: invalid signature", " ".join(ek.verify(self.root)["problems"]))

    def test_owner_rotation_is_approved_by_the_old_owner_key(self):
        keygen(self.root / "new_owner")
        ek.rotate("owner", self.root / "new_owner.pub", self.root, when="20990101000000Z")
        ek.record(
            "owner", "keys", "New owner key, signed with the old one.", root=self.root, when="2099-01-01T00:00:01Z"
        )
        os.environ["EILIKRINEIA_KEY_OWNER"] = str(self.root / "new_owner")
        try:
            ek.record("owner", "decision", "First act of the new key.", root=self.root, when="2099-01-02T00:00:00Z")
        finally:
            os.environ.pop("EILIKRINEIA_KEY_OWNER")
        self.assertTrue(ek.verify(self.root)["ok"], ek.verify(self.root)["problems"])
        ek.record("owner", "decision", "The retired key again.", root=self.root, when="2099-01-03T00:00:00Z")
        self.assertIn("#4: invalid signature", " ".join(ek.verify(self.root)["problems"]))

    def test_owner_rotation_signed_only_by_the_new_key_is_not_trusted(self):
        keygen(self.root / "new_owner")
        ek.rotate("owner", self.root / "new_owner.pub", self.root, when="20990101000000Z")
        os.environ["EILIKRINEIA_KEY_OWNER"] = str(self.root / "new_owner")
        try:
            ek.record("owner", "keys", "Self-approved key.", root=self.root, when="2099-01-01T00:00:01Z")
        finally:
            os.environ.pop("EILIKRINEIA_KEY_OWNER")
        self.assertIn("differs from the list last signed", " ".join(ek.verify(self.root)["problems"]))

    def test_rotation_handles_lines_without_options_and_comments(self):
        signers = self.root / "keys" / "allowed_signers"
        bare = [ln.replace(' namespaces="eilikrineia"', "") if ln.startswith("agent ") else ln
                for ln in signers.read_text().splitlines()]  # fmt: skip
        signers.write_text("# keys of this ledger\n\n" + "\n".join(bare) + "\n")
        ek.record("owner", "keys", "Agent key without options.", root=self.root)
        keygen(self.root / "new_agent")
        ek.rotate("agent", self.root / "new_agent.pub", self.root, when="20990101000000Z")
        lines = signers.read_text().splitlines()
        self.assertEqual(lines[:2], ["# keys of this ledger", ""])
        old = next(ln for ln in lines if ln.startswith("agent ") and "valid-after" not in ln)
        self.assertEqual(old.split()[1:3], ['valid-before="20990101000000Z"', "ssh-ed25519"])
        ek.record("owner", "keys", "New agent key.", root=self.root, when="2099-01-01T00:00:01Z")
        ek.record("agent", "opinion", "signed with a retired key", root=self.root, when="2099-01-02T00:00:00Z")
        self.assertIn("#4: invalid signature", " ".join(ek.verify(self.root)["problems"]))

    def test_rotation_refuses_unparseable_line_and_writes_nothing(self):
        signers = self.root / "keys" / "allowed_signers"
        signers.write_text(signers.read_text() + "agent\n")
        before = signers.read_bytes()
        keygen(self.root / "new_agent")
        with self.assertRaises(SystemExit):
            ek.rotate("agent", self.root / "new_agent.pub", self.root, when="20990101000000Z")
        self.assertEqual(signers.read_bytes(), before)

    def test_init_again_only_appends(self):
        before = (self.root / "keys" / "allowed_signers").read_text()
        self.assertEqual(ek.init(self.root)["added"], [])
        self.assertEqual((self.root / "keys" / "allowed_signers").read_text(), before)


class Tampering(Ledger):
    def test_edited_deleted_backdated_and_wrong_role_entries_are_caught(self):
        for i in range(3):
            ek.record("agent", "opinion", f"note {i}", root=self.root)
        chain = self.root / "chain"
        e = json.loads((chain / "000002.json").read_text())
        e["type"] = "measured"
        (chain / "000002.json").write_text(json.dumps(e))
        self.assertIn("entry altered", " ".join(ek.verify(self.root)["problems"]))
        (chain / "000003.json").unlink()
        self.assertFalse(ek.verify(self.root)["ok"])

    def test_private_text_must_match_commitment(self):
        self.measured()
        f = self.root / "private" / "texts" / "000002.json"
        d = json.loads(f.read_text())
        d["text"] = "The suite ran 26 tests."
        f.write_text(json.dumps(d))
        self.assertIn("does not match the public commitment", " ".join(ek.verify(self.root, private=True)["problems"]))

    def test_vault_copy_is_what_counts_and_tampering_it_is_caught(self):
        self.measured()
        self.log.write_text("rewritten after the fact\n")  # the original may change; the vault copy is the proof
        self.assertTrue(ek.verify(self.root, private=True)["ok"])
        for copy in (self.root / "private" / "vault").iterdir():
            copy.chmod(0o644)
            copy.write_bytes(b"forged")
        self.assertFalse(ek.verify(self.root, private=True)["ok"])

    def test_vault_is_compressed_and_old_plain_copies_still_count(self):
        digest = ek.vault_put(self.log, self.root)
        stored = (self.root / "private" / "vault" / f"{digest}.gz").stat().st_size
        self.assertLess(stored * 4, self.log.stat().st_size)  # text shrinks more than 4x
        plain = Path(self._d.name) / "plain.txt"
        plain.write_text("a copy made before compression existed\n" * 50)
        old = ek.sha256_file(plain)
        shutil.copyfile(plain, self.root / "private" / "vault" / old)  # legacy layout: plain file named by hash
        self.assertEqual(ek.vault_read(old, self.root), plain.read_bytes())
        self.assertEqual(ek.compact(self.root), {"compressed": 1})
        self.assertEqual(ek.vault_read(old, self.root), plain.read_bytes())


class Claims(Ledger):
    def test_mechanical_predicates(self):
        self.measured(25)
        self.measured(26)
        texts = sorted((self.root / "private" / "texts").glob("*.json"))
        results = [ek.check_claim(json.loads(t.read_text())["claims"][0], self.root)[0] for t in texts[1:]]
        self.assertEqual(results, [True, False])
        cfg = Path(self._d.name) / "c.json"
        cfg.write_text(json.dumps({"tests": {"passed": 25}}))
        eq = ek.build_claim(
            {"predicate": "equals", "args": {"value": 25}, "evidence": f"{cfg}#/tests/passed"}, self.root
        )
        self.assertTrue(ek.check_claim(eq, self.root)[0])

    def test_excerpt_larger_than_limit_is_refused(self):
        with self.assertRaises(SystemExit):
            ek.record("agent", "assertion", "the whole log says so", root=self.root,
                      claims=[{"predicate": "semantic", "evidence": str(self.log)}])  # fmt: skip


class Audit(Ledger):
    def test_model_reads_only_excerpts_and_mechanics_decide(self):
        self.measured(26)  # wrong number: code alone decides
        ek.record("agent", "assertion", "Line 3 reports the test count.", root=self.root,
                  claims=[{"predicate": "semantic", "evidence": f"{self.log}:2-3"}])  # fmt: skip
        ek.record("agent", "opinion", "I think it will scale.", root=self.root)
        prompts = []

        def fake(prompt, auditor):
            prompts.append(prompt)
            return '{"verdict": "supported", "reason": "line 3: Ran 25 tests"}'

        size = len(ek.entries(self.root))
        out = ek.audit(self.root, ask=fake)
        verdicts = {a["seq"]: a["verdict"] for a in out["audited"]}
        self.assertEqual(verdicts, {2: "unsupported", 3: "supported"})  # opinion and owner genesis not judged
        self.assertTrue(all(len(p) < 4000 for p in prompts))  # never a whole file
        self.assertTrue(all("line 300" not in p for p in prompts))
        chain = ek.entries(self.root)
        self.assertEqual(len(chain), size + 1)  # ONE checkpoint carries every verdict of the run
        self.assertEqual(chain[-1]["type"], "checkpoint")
        self.assertTrue(ek.verify(self.root, private=True)["ok"])

    def test_audit_is_incremental_and_idle_adds_nothing(self):
        self.measured()
        ek.audit(self.root, ask=lambda p, a: '{"verdict": "supported", "reason": "ok"}')
        size, calls = len(ek.entries(self.root)), []
        out = ek.audit(self.root, ask=lambda p, a: calls.append(p) or '{"verdict": "supported", "reason": "ok"}')
        self.assertEqual((out, calls, len(ek.entries(self.root))), ({"audited": [], "checkpoint": None}, [], size))

    def test_parse_verdict(self):
        self.assertEqual(
            ek.parse_verdict('{"text": "{\\"verdict\\":\\"partial\\",\\"reason\\":\\"x\\"}"}')["verdict"], "partial"
        )
        with self.assertRaises(SystemExit):
            ek.parse_verdict('{"verdict": "maybe"}')


class Witness(Ledger):
    def test_rewriting_the_unpublished_tail_is_caught(self):
        file = Path(self._d.name) / "witness.json"
        ek.record("agent", "opinion", "first", root=self.root)
        self.assertEqual(ek.witness(self.root, file)["diverged"], [])
        (self.root / "chain" / "000002.json").unlink()
        (self.root / "private" / "texts" / "000002.json").unlink()
        ek.record("agent", "opinion", "first, rewritten", root=self.root)
        self.assertTrue(ek.verify(self.root, private=True)["ok"])  # the chain alone cannot tell
        out = ek.witness(self.root, file)
        self.assertEqual([d["seq"] for d in out["diverged"]], [2])
        self.assertIsNotNone(out["alarm"])


class PinnedCode(Ledger):
    def test_auditor_code_changes_only_with_owner_signature(self):
        code = self.root / "eilikrineia.py"
        self.assertTrue(ek.pinned_ok(code, self.root))
        code.write_text(code.read_text() + "\n# agent edit\n")
        self.assertFalse(ek.pinned_ok(code, self.root))
        ek.record("owner", "code", "I approve this code.", root=self.root)
        self.assertTrue(ek.pinned_ok(code, self.root))

    def forge(self, fields, sign_as=None):
        """Append a hand-made entry after the head; sign it with ``sign_as`` or leave it unsigned."""
        head = ek.entries(self.root)[-1]
        e = {"seq": head["seq"] + 1, "time": ek.now_utc(), "role": "agent", "type": "opinion",
             "commitment": "00" * 32, "attachments": [], "prev": head["hash"], **fields}  # fmt: skip
        e["hash"] = ek.entry_hash(e)
        e["signature"] = ek.sign(sign_as, e["hash"], self.root) if sign_as else "none"
        (self.root / "chain" / f"{e['seq']:06d}.json").write_text(json.dumps(e))
        return e

    def test_unsigned_raw_entry_cannot_pin_code(self):
        evil = self.root / "evil.py"
        evil.write_text("print('not signed by the owner')\n")
        self.forge({"role": "owner", "type": "code", "code_sha256": ek.sha256_file(evil)})
        self.assertFalse(ek.pinned_ok(evil, self.root))

    def test_owner_entry_replayed_at_the_end_cannot_pin_old_code(self):
        code = self.root / "eilikrineia.py"
        old = code.read_bytes()
        genesis = ek.entries(self.root)[0]
        code.write_text(code.read_text() + "\n# new owner-approved code\n")
        ek.record("owner", "code", "I approve the new code.", root=self.root)
        (self.root / "chain" / f"{len(ek.entries(self.root)) + 1:06d}.json").write_text(json.dumps(genesis))
        code.write_bytes(old)
        self.assertFalse(ek.pinned_ok(code, self.root))

    def test_agent_cannot_move_the_key_list_or_the_code(self):
        keygen(self.root / "fake_owner")
        kind, body = (self.root / "fake_owner.pub").read_text().split()[:2]
        signers = self.root / "keys" / "allowed_signers"
        signers.write_text(signers.read_text() + f'owner namespaces="eilikrineia" {kind} {body}\n')
        self.forge({"signers_sha256": ek.sha256_file(signers)}, sign_as="agent")
        problems = " ".join(ek.verify(self.root)["problems"])
        self.assertIn("differs from the list last signed", problems)
        self.assertIn("signers_sha256 outside an owner", problems)
        evil = self.root / "evil.py"
        evil.write_text("print('planted owner key')\n")
        os.environ["EILIKRINEIA_KEY_OWNER"] = str(self.root / "fake_owner")
        try:
            self.forge({"role": "owner", "type": "code", "code_sha256": ek.sha256_file(evil)}, sign_as="owner")
        finally:
            os.environ.pop("EILIKRINEIA_KEY_OWNER")
        self.assertFalse(ek.pinned_ok(evil, self.root))

    def test_owner_entry_with_a_replaced_signature_pins_nothing(self):
        code = self.root / "eilikrineia.py"
        old = code.read_bytes()
        code.write_text(code.read_text() + "\n# new owner-approved code\n")
        e = ek.record("owner", "code", "I approve the new code.", root=self.root)
        path = self.root / "chain" / f"{e['seq']:06d}.json"
        stripped = json.loads(path.read_text())
        stripped["signature"] = ek.sign("agent", stripped["hash"], self.root)  # the hash is unchanged
        path.write_text(json.dumps(stripped))
        self.assertIsNone(ek.committed_code(ek.entries(self.root), self.root))
        code.write_bytes(old)
        self.assertFalse(ek.pinned_ok(code, self.root))

    def test_unknown_type_role_and_field_are_problems(self):
        self.forge({"type": "receipt", "status": "located_and_matched"}, sign_as="agent")
        problems = " ".join(ek.verify(self.root)["problems"])
        self.assertIn("unknown type 'receipt'", problems)
        self.assertIn("unknown field 'status'", problems)

    def test_witness_anchors_the_code_against_a_forged_genesis_and_a_cut_tail(self):
        code = self.root / "eilikrineia.py"
        old = code.read_bytes()
        ek.record("agent", "opinion", "work", root=self.root)
        code.write_text(code.read_text() + "\n# newer owner-approved code\n")
        ek.record("owner", "code", "Newer code.", root=self.root)
        witness = Path(self._d.name) / "witness.json"
        ek.witness(self.root, witness)
        os.environ["EILIKRINEIA_WITNESS"] = str(witness)
        try:
            self.assertTrue(ek.pinned_ok(code, self.root))
            chain = sorted((self.root / "chain").glob("*.json"))
            tail = {f: f.read_text() for f in chain[2:]}
            for f in tail:  # cut the tail: the genesis-pinned older code would come back
                f.unlink()
            older = Path(self._d.name) / "older.py"
            older.write_bytes(old)
            self.assertFalse(ek.pinned_ok(older, self.root))
            for f, text in tail.items():
                f.write_text(text)
            keygen(self.root / "attacker")  # a genesis signed by an attacker key, with its key list planted
            kind, body = (self.root / "attacker.pub").read_text().split()[:2]
            keep = [
                ln
                for ln in (self.root / "keys/allowed_signers").read_text().splitlines()
                if not ln.startswith("owner ")
            ]
            planted = "\n".join(keep + [f'owner namespaces="eilikrineia" {kind} {body}']) + "\n"
            digest = ek.sha256_bytes(planted.encode())
            (self.root / "keys" / f"allowed_signers.{digest}").write_text(planted)
            evil = self.root / "evil.py"
            evil.write_text("print('attacker code')\n")
            g = {"seq": 1, "time": ek.now_utc(), "role": "owner", "type": "genesis", "commitment": "00" * 32,
                 "attachments": [], "prev": ek.GENESIS_PREV, "signers_sha256": digest,
                 "code_sha256": ek.sha256_file(evil)}  # fmt: skip
            g["hash"] = ek.entry_hash(g)
            os.environ["EILIKRINEIA_KEY_OWNER"] = str(self.root / "attacker")
            g["signature"] = ek.sign("owner", g["hash"], self.root)
            os.environ.pop("EILIKRINEIA_KEY_OWNER")
            (self.root / "chain" / "000001.json").write_text(json.dumps(g))
            self.assertFalse(ek.pinned_ok(evil, self.root))
        finally:
            os.environ.pop("EILIKRINEIA_WITNESS", None)
            os.environ.pop("EILIKRINEIA_KEY_OWNER", None)

    def test_backdated_owner_code_entry_does_not_count(self):
        evil = self.root / "evil.py"
        evil.write_text("print('backdated')\n")
        ek.record("agent", "opinion", "now", root=self.root, when="2099-01-01T00:00:00Z")
        self.forge({"role": "owner", "type": "code", "code_sha256": ek.sha256_file(evil),
                    "time": "2000-01-01T00:00:00Z"}, sign_as="owner")  # fmt: skip
        self.assertFalse(ek.pinned_ok(evil, self.root))

    def test_malformed_entries_do_not_crash_the_pinned_check(self):
        evil = self.root / "evil.py"
        evil.write_text("print('malformed')\n")
        e = self.forge({"role": "owner", "type": "code", "code_sha256": ek.sha256_file(evil)})
        e["signature"] = []
        (self.root / "chain" / "000002.json").write_text(json.dumps(e))
        self.assertFalse(ek.pinned_ok(evil, self.root))
        (self.root / "chain" / "000002.json").write_text("[]")
        self.assertFalse(ek.pinned_ok(self.root / "eilikrineia.py", self.root))


class Publish(Ledger):
    def setUp(self):
        super().setUp()
        self.remote = Path(self._d.name) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        git = ["git", "-C", str(self.root)]
        subprocess.run(git + ["init", "-q", "-b", "main"], check=True)
        subprocess.run(git + ["config", "user.email", "t@t"], check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        subprocess.run(git + ["remote", "add", "origin", str(self.remote)], check=True)
        (self.root / ".gitignore").write_text("private/\n")
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "start"], check=True)
        subprocess.run(git + ["push", "-q", "origin", "main"], check=True, env=dict(os.environ, DOCTRINE_PUSH_OK="1"))
        self._stamp, ek.stamp = ek.stamp, lambda root=None: {"stamp": None}

    def tearDown(self):
        ek.stamp = self._stamp
        super().tearDown()

    def test_publishes_chain_never_private(self):
        ek.record("agent", "opinion", "a secret sentence", root=self.root)
        self.assertTrue(ek.publish(self.root)["pushed"])
        listed = subprocess.run(["git", "--git-dir", str(self.remote), "ls-tree", "-r", "--name-only", "main"],
                                capture_output=True, text=True).stdout.split()  # fmt: skip
        self.assertIn("chain/000002.json", listed)
        self.assertFalse(any(n.startswith("private/") for n in listed))
        grep = subprocess.run(["git", "--git-dir", str(self.remote), "grep", "-l", "secret sentence", "main"],
                              capture_output=True, text=True)  # fmt: skip
        self.assertEqual(grep.stdout, "")

    def test_failed_verification_publishes_nothing(self):
        f = self.root / "chain" / "000001.json"
        e = json.loads(f.read_text())
        e["role"] = "agent"
        f.write_text(json.dumps(e))
        with self.assertRaises(SystemExit):
            ek.publish(self.root)

    def test_failed_fetch_pushes_nothing(self):
        ek.record("agent", "opinion", "waiting for a reachable remote", root=self.root)
        git = ["git", "-C", str(self.root)]
        subprocess.run(git + ["remote", "set-url", "origin", str(Path(self._d.name) / "missing.git")], check=True)
        with self.assertRaises(SystemExit) as caught:
            ek.publish(self.root)
        self.assertIn("fetch failed", str(caught.exception))
        listed = subprocess.run(["git", "--git-dir", str(self.remote), "ls-tree", "-r", "--name-only", "main"],
                                capture_output=True, text=True).stdout.split()  # fmt: skip
        self.assertNotIn("chain/000002.json", listed)


class ReadmeNumbers(unittest.TestCase):
    def test_readme_test_count_matches_the_suite(self):
        import re

        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
        badge = int(re.search(r"unittest_\((\d+)_passing\)", readme).group(1))
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent))
        self.assertEqual(badge, suite.countTestCases())

    def test_readme_excerpt_limit_matches_the_code(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
        self.assertIn(f"{ek.MAX_EXCERPT:,} characters", readme)


if __name__ == "__main__":
    unittest.main()
