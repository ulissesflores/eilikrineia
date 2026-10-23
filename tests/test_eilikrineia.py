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


class IniciarDeNovoTest(Base):
    def test_iniciar_de_novo_so_acrescenta_e_nao_recria_chave(self):
        import subprocess
        nova = self.raiz / "nova_auditor"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(nova)], check=True)
        ek.rotacionar("auditor", Path(str(nova) + ".pub"), self.raiz, agora="20261023120000Z")
        (self.raiz / "privado" / "chaves" / "auditor").unlink()  # como o instalador faz
        antes = (self.raiz / "chaves" / "allowed_signers").read_text()
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.raiz / "privado" / "chaves" / "ulisses")], check=True)
        r = ek.iniciar(self.raiz)
        depois = (self.raiz / "chaves" / "allowed_signers").read_text()
        self.assertEqual(r["acrescentados"], ["ulisses"])
        self.assertTrue(depois.startswith(antes))  # nada reescrito
        self.assertFalse((self.raiz / "privado" / "chaves" / "auditor").exists())  # não recriou


class GeneseDoDonoTest(Base):
    SENHA = "senha-so-do-dono"

    def setUp(self):
        super().setUp()
        import os, subprocess
        (self.raiz / "PROTOCOLO.md").write_text("protocolo\n", encoding="utf-8")
        (self.raiz / "eilikrineia.py").write_text("codigo\n", encoding="utf-8")
        chave = self.raiz / "privado" / "chaves" / "ulisses"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", self.SENHA, "-f", str(chave)], check=True)
        askpass = self.raiz / "askpass.sh"  # simula o dono digitando a senha
        askpass.write_text(f"#!/bin/sh\necho {self.SENHA}\n")
        askpass.chmod(0o755)
        self._env = {k: os.environ.get(k) for k in ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "DISPLAY")}
        os.environ.update(SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE="force", DISPLAY=":0")

    def tearDown(self):
        import os
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def test_genese_assume_a_cadeia_antiga_e_vira_raiz(self):
        self.reg(texto="antes da gênese")
        topo_antigo = ek.entradas(self.raiz)[-1]["hash"]
        g = ek.genese(self.raiz)
        self.assertEqual(g["seq"], 1)
        self.assertEqual(g["antecessora"]["topo"], topo_antigo)
        e1 = ek.entradas(self.raiz)[0]
        self.assertEqual((e1["tipo"], e1["papel"]), ("genese", "ulisses"))
        v = ek.verificar(self.raiz, privado=True)
        self.assertTrue(v["ok"], v["problemas"])
        self.assertEqual(v["raiz_de_confianca"], "gênese do dono")
        velho = ek.verificar(self.raiz / "historico" / "v0", privado=True)
        self.assertTrue(velho["ok"], velho["problemas"])
        self.assertEqual(velho["topo"], topo_antigo)
        self.reg(texto="depois da gênese")
        self.assertTrue(ek.verificar(self.raiz, privado=True)["ok"])

    def test_agente_nao_assina_genese_nem_troca_chave_sem_o_dono(self):
        import subprocess
        with self.assertRaises(SystemExit):
            ek.registrar("claude", "genese", "falsa", [self.ev], raiz=self.raiz)
        ek.genese(self.raiz)
        intrusa = self.raiz / "intrusa"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(intrusa)], check=True)
        lista = self.raiz / "chaves" / "allowed_signers"
        pub = Path(str(intrusa) + ".pub").read_text().split()
        lista.write_text(lista.read_text() + f'ulisses namespaces="eilikrineia" {pub[0]} {pub[1]}\n')
        v = ek.verificar(self.raiz)
        self.assertTrue(any("diferente da última assinada pelo dono" in p for p in v["problemas"]))
        with self.assertRaises(SystemExit):
            self.reg(texto="tentativa depois de mexer na lista")

    def test_troca_de_chave_assinada_pelo_dono_vale(self):
        import subprocess
        ek.genese(self.raiz)
        nova = self.raiz / "nova_auditor"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(nova)], check=True)
        ek.rotacionar("auditor", Path(str(nova) + ".pub"), self.raiz)
        ek.registrar("ulisses", "chaves", "troca da chave do auditor", [self.raiz / "chaves" / "allowed_signers"], raiz=self.raiz)
        self.reg(texto="segue normal")
        self.assertTrue(ek.verificar(self.raiz, privado=True)["ok"])


class TestemunhaTest(Base):
    def test_reescrever_trecho_nao_publicado_e_acusado_pela_testemunha(self):
        testemunha = self.raiz.parent / (self.raiz.name + "-testemunha.json")  # fora do alcance do agente, na prática
        self.reg(texto="primeira")
        self.reg(texto="segunda, que eu gostaria de trocar")
        r = ek.vigiar(self.raiz, testemunha)
        self.assertEqual((r["novas_testemunhadas"], r["divergencias"]), (2, []))
        # o agente apaga a última entrada (ainda não publicada) e registra outra no lugar
        (self.raiz / "cadeia" / "000002.json").unlink()
        (self.raiz / "privado" / "textos" / "000002.json").unlink()
        self.reg(texto="segunda, reescrita")
        self.assertTrue(ek.verificar(self.raiz, privado=True)["ok"])  # a cadeia sozinha não percebe
        r = ek.vigiar(self.raiz, testemunha)
        self.assertEqual([d["seq"] for d in r["divergencias"]], [2])  # a testemunha percebe
        self.assertIsNotNone(r["alarme_registrado"])
        self.assertEqual(ek.entradas(self.raiz)[-1]["tipo"], "auditoria")
        testemunha.unlink()


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

    def test_opiniao_nao_vai_ao_auditor(self):
        self.reg(tipo="opiniao", texto="acho que vai melhorar", evidencias=[])
        r = ek.auditar(self.raiz, chamar=lambda p, a: self.fail("opinião não deveria ser julgada como fato"))
        self.assertEqual(r["auditorias"], [])

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
