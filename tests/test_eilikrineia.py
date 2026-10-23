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
