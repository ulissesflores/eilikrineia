import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import eilikrineia as ek  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.raiz = Path(self._d.name)
        ek.iniciar(self.raiz)
        self.ev = self.raiz / "evidencia.txt"
        self.ev.write_text("saída real do comando: 202 testes OK\n", encoding="utf-8")

    def tearDown(self):
        self._d.cleanup()

    def reg(self, **kw):
        base = dict(papel="claude", tipo="fato-medido", texto="Suíte passou: 202 testes.", evidencias=[self.ev], raiz=self.raiz)
        base.update(kw)
        return ek.registrar(**base)


class CadeiaTest(Base):
    def test_cadeia_integra_e_encadeada(self):
        a = self.reg()
        b = self.reg(tipo="opiniao", texto="Acho que a navegação vai ajudar.", evidencias=[])
        es = ek.entradas(self.raiz)
        self.assertEqual(es[0]["anterior"], ek.GENESE)
        self.assertEqual(es[1]["anterior"], a["hash"])
        self.assertEqual(b["seq"], 2)
        v = ek.verificar(self.raiz, privado=True)
        self.assertTrue(v["ok"], v["problemas"])

    def test_texto_nao_vai_para_a_cadeia_publica(self):
        self.reg(texto="segredo que não pode aparecer")
        publico = (self.raiz / "cadeia" / "000001.json").read_text(encoding="utf-8")
        self.assertNotIn("segredo", publico)
        self.assertNotIn(str(self.ev), publico)

    def test_regras_de_registro(self):
        with self.assertRaises(SystemExit):
            self.reg(evidencias=[])  # fato sem evidência
        with self.assertRaises(SystemExit):
            self.reg(tipo="decisao")  # decisão só pela chave dele
        with self.assertRaises(SystemExit):
            self.reg(tipo="correcao", evidencias=[], corrige="f" * 64)  # corrige hash inexistente

    def test_correcao_mantem_a_antiga(self):
        a = self.reg(texto="A mudança piorou o resultado.")
        ek.registrar("claude", "correcao", "Errado: o teste usou material sem relação com a notícia.", [self.ev],
                     corrige=a["hash"], raiz=self.raiz)
        self.assertEqual(len(ek.entradas(self.raiz)), 2)
        self.assertTrue(ek.verificar(self.raiz, privado=True)["ok"])


class AdulteracaoTest(Base):
    def test_editar_entrada_publica_e_acusado(self):
        self.reg()
        self.reg(texto="segunda")
        arq = self.raiz / "cadeia" / "000001.json"
        e = json.loads(arq.read_text())
        e["tipo"] = "opiniao"
        arq.write_text(json.dumps(e))
        v = ek.verificar(self.raiz)
        self.assertFalse(v["ok"])
        self.assertTrue(any("alterada" in p for p in v["problemas"]))

    def test_trocar_texto_privado_e_acusado(self):
        self.reg()
        arq = self.raiz / "privado" / "textos" / "000001.json"
        d = json.loads(arq.read_text())
        d["texto"] = "Suíte passou: 203 testes."
        arq.write_text(json.dumps(d))
        v = ek.verificar(self.raiz, privado=True)
        self.assertTrue(any("não bate com o compromisso" in p for p in v["problemas"]))

    def test_original_que_muda_depois_vale_pela_copia_do_acervo(self):
        self.reg()
        self.ev.write_text("outra coisa\n", encoding="utf-8")
        v = ek.verificar(self.raiz, privado=True)
        self.assertTrue(v["ok"], v["problemas"])
        self.assertTrue(any("vale a cópia do acervo" in a for a in v["avisos"]))

    def test_mexer_na_copia_do_acervo_e_acusado(self):
        self.reg()
        copia = next((self.raiz / "privado" / "acervo").iterdir())
        copia.chmod(0o644)
        copia.write_text("forjada\n", encoding="utf-8")
        self.ev.write_text("também mudou\n", encoding="utf-8")
        v = ek.verificar(self.raiz, privado=True)
        self.assertTrue(any("evidência perdida" in p for p in v["problemas"]))

    def test_evidencia_perdida_em_entrada_corrigida_fica_reconhecida(self):
        a = self.reg()
        copia = next((self.raiz / "privado" / "acervo").iterdir())
        copia.chmod(0o644)
        copia.unlink()
        self.ev.write_text("mudou\n", encoding="utf-8")
        self.assertFalse(ek.verificar(self.raiz, privado=True)["ok"])
        ev2 = self.raiz / "ev2.txt"
        ev2.write_text("explicação\n", encoding="utf-8")
        ek.registrar("claude", "correcao", "A evidência da entrada 1 foi perdida.", [ev2], corrige=a["hash"], raiz=self.raiz)
        v = ek.verificar(self.raiz, privado=True)
        self.assertTrue(v["ok"], v["problemas"])
        self.assertTrue(v["reconhecidos"])

    def test_apagar_entrada_do_meio_e_acusado(self):
        for t in ("a", "b", "c"):
            self.reg(texto=t)
        (self.raiz / "cadeia" / "000002.json").unlink()
        self.assertFalse(ek.verificar(self.raiz)["ok"])

    def test_assinar_com_chave_de_outro_papel_e_acusado(self):
        self.reg()
        arq = self.raiz / "cadeia" / "000001.json"
        e = json.loads(arq.read_text())
        e["assinatura"] = ek.assinar("auditor", e["hash"], self.raiz)  # papel diz claude, assinou o auditor
        arq.write_text(json.dumps(e))
        v = ek.verificar(self.raiz)
        self.assertTrue(any("assinatura inválida" in p for p in v["problemas"]))


class RotacaoTest(Base):
    def test_chave_aposentada_nao_assina_entrada_nova(self):
        import os, subprocess
        ek.registrar("claude", "opiniao", "antes da troca", [], raiz=self.raiz, agora="2026-10-23T10:00:00Z")
        nova = self.raiz / "nova_claude"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(nova)], check=True)
        ek.rotacionar("claude", Path(str(nova) + ".pub"), self.raiz, agora="20261023120000Z")
        # chave antiga, entrada depois da troca -> reprovada
        ek.registrar("claude", "opiniao", "forjada com a chave velha", [], raiz=self.raiz, agora="2026-10-23T13:00:00Z")
        v = ek.verificar(self.raiz)
        self.assertTrue(any("#2: assinatura inválida" in p for p in v["problemas"]), v["problemas"])
        self.assertFalse(any(p.startswith("#1:") for p in v["problemas"]))  # entrada antiga segue válida

    def test_chave_nova_por_variavel_de_ambiente_vale(self):
        import os, subprocess
        nova = self.raiz / "fora" / "auditor"
        nova.parent.mkdir()
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(nova)], check=True)
        ek.rotacionar("auditor", Path(str(nova) + ".pub"), self.raiz, agora="20200101000000Z")
        self.reg()
        os.environ["EILIKRINEIA_CHAVE_AUDITOR"] = str(nova)
        try:
            ek.auditar(self.raiz, chamar=lambda p, a: ("x", '{"veredito": "sustentada", "motivo": "ok"}'))
        finally:
            del os.environ["EILIKRINEIA_CHAVE_AUDITOR"]
        self.assertTrue(ek.verificar(self.raiz, privado=True)["ok"])

    def test_data_retroativa_e_acusada(self):
        ek.registrar("claude", "opiniao", "a", [], raiz=self.raiz, agora="2026-10-23T10:00:00Z")
        ek.registrar("claude", "opiniao", "b", [], raiz=self.raiz, agora="2026-10-22T10:00:00Z")
        self.assertTrue(any("retroativa" in p for p in ek.verificar(self.raiz)["problemas"]))


class AuditorTest(Base):
    def test_auditor_assina_veredito_e_encadeia(self):
        self.reg()
        prompts = []

        def falso(prompt, auditor):
            prompts.append(prompt)
            return "grok-falso", json.dumps({"veredito": "sustentada", "motivo": "a saída mostra 202 testes OK"})
        r = ek.auditar(self.raiz, chamar=falso)
        self.assertEqual(r["auditorias"][0]["veredito"], "sustentada")
        self.assertIn("202 testes OK", prompts[0])
        es = ek.entradas(self.raiz)
        self.assertEqual(es[-1]["tipo"], "auditoria")
        self.assertEqual(es[-1]["papel"], "auditor")
        self.assertEqual(es[-1]["audita"], es[0]["hash"])
        self.assertTrue(ek.verificar(self.raiz, privado=True)["ok"])
        self.assertEqual(ek.auditar(self.raiz, chamar=falso)["auditorias"], [])  # não audita de novo

    def test_mecanica_falha_vira_auditoria_negativa(self):
        self.reg()
        copia = next((self.raiz / "privado" / "acervo").iterdir())
        copia.chmod(0o644)
        copia.write_text("adulterada\n", encoding="utf-8")
        self.ev.write_text("adulterada\n", encoding="utf-8")
        r = ek.auditar(self.raiz, chamar=lambda p, a: self.fail("não deveria chamar o modelo"))
        self.assertFalse(r["mecanica"]["ok"])

    def test_extrair_veredito_de_envelopes(self):
        self.assertEqual(ek.extrair_veredito('{"structured_output": {"veredito": "parcial", "motivo": "x"}}')["veredito"], "parcial")
        self.assertEqual(ek.extrair_veredito('texto antes {"veredito": "nao_sustentada", "motivo": "y"} depois')["veredito"],
                         "nao_sustentada")
        with self.assertRaises(SystemExit):
            ek.extrair_veredito('{"veredito": "talvez"}')


class PublicarTest(Base):
    def setUp(self):
        super().setUp()
        import subprocess
        self.sp = subprocess
        self.remoto = self.raiz.parent / (self.raiz.name + "-remoto.git")
        subprocess.run(["git", "init", "-q", "--bare", str(self.remoto)], check=True)
        subprocess.run(["git", "-C", str(self.raiz), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.raiz), "remote", "add", "origin", str(self.remoto)], check=True)
        (self.raiz / ".gitignore").write_text("privado/\n", encoding="utf-8")
        self._carimbar = ek.carimbar
        ek.carimbar = lambda raiz=None: {"carimbo": None}

    def tearDown(self):
        ek.carimbar = self._carimbar
        import shutil
        shutil.rmtree(self.remoto, ignore_errors=True)
        super().tearDown()

    def test_publica_cadeia_e_nunca_o_privado(self):
        self.reg(texto="segredo que não pode sair")
        r = ek.publicar(self.raiz)
        self.assertTrue(r["push"])
        arquivos = self.sp.run(["git", "--git-dir", str(self.remoto), "ls-tree", "-r", "--name-only", "HEAD"],
                               capture_output=True, text=True).stdout.split()
        self.assertIn("cadeia/000001.json", arquivos)
        self.assertFalse(any(a.startswith("privado/") for a in arquivos))
        conteudo = self.sp.run(["git", "--git-dir", str(self.remoto), "grep", "-l", "segredo", "HEAD"],
                               capture_output=True, text=True).stdout
        self.assertEqual(conteudo, "")

    def test_verificador_reprovado_nao_publica(self):
        self.reg()
        arq = self.raiz / "cadeia" / "000001.json"
        e = json.loads(arq.read_text())
        e["tipo"] = "opiniao"
        arq.write_text(json.dumps(e))
        with self.assertRaises(SystemExit):
            ek.publicar(self.raiz)
        log = self.sp.run(["git", "--git-dir", str(self.remoto), "log", "--oneline"], capture_output=True, text=True)
        self.assertNotEqual(log.returncode, 0)  # remoto continua vazio


if __name__ == "__main__":
    unittest.main()
