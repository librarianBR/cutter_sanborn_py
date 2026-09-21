"""Testes da interface (sem abrir janela). Usa um Page simulado."""
import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace

_TMP = tempfile.mkdtemp()
os.environ["CUTTER_SANBORN_HOME"] = _TMP          # não mexe no estado real do usuário

import flet as ft                                  # noqa: E402

import app_flet                                    # noqa: E402
import cutter_sanborn as cs                        # noqa: E402


class PageFalso:
    def __init__(self):
        self.controls, self.services = [], []
        self.window = SimpleNamespace()
        self.dialogos = []
        self.atualizacoes = 0
        self.theme_mode = ft.ThemeMode.SYSTEM

    def add(self, *c):
        self.controls.extend(c)

    def update(self):
        self.atualizacoes += 1

    def show_dialog(self, d):
        self.dialogos.append(d)


def textos(controle, acc=None):
    """Coleta todos os textos de uma árvore de controles."""
    acc = [] if acc is None else acc
    if isinstance(controle, ft.Text):
        acc.append(controle.value)
    for nome in ("content", "controls", "cells", "rows", "title", "subtitle", "label", "tabs"):
        filho = getattr(controle, nome, None)
        if isinstance(filho, ft.Control):
            textos(filho, acc)
        elif isinstance(filho, (list, tuple)):
            for f in filho:
                if isinstance(f, ft.Control):
                    textos(f, acc)
    return acc


class Base(unittest.TestCase):
    def setUp(self):
        aj = dict(app_flet.AJUSTES_PADRAO)
        app_flet.aplicar_ajustes(aj)
        if os.path.exists(app_flet.ARQ_ESTADO):
            os.remove(app_flet.ARQ_ESTADO)
        self.page = PageFalso()
        self.app = app_flet.CutterApp(self.page)
        self.app.montar()


class TestMontagem(Base):
    def test_monta_sem_erros(self):
        self.assertIsNone(self.app.erro_tabela.strip() or None)
        self.assertIsNotNone(self.app.tabela)
        self.assertTrue(self.page.controls)
        self.assertIn(self.app.clip, self.page.services)

    def test_resumo_de_integridade(self):
        self.assertIn("12.329", self.app.resumo_integridade.value)
        self.assertTrue(self.app.lista_integridade.controls)

    def test_falha_de_tabela_mostra_erro_em_vez_de_quebrar(self):
        original = cs.TABELA_PADRAO
        try:
            cs.TABELA_PADRAO = original.with_name("nao_existe.json")
            page = PageFalso()
            app = app_flet.CutterApp(page)
            app.montar()
            self.assertIsNone(app.tabela)
            self.assertTrue(any("Não foi possível" in t for c in page.controls for t in textos(c)))
        finally:
            cs.TABELA_PADRAO = original


class TestGerar(Base):
    def preencher(self, autor, titulo="", **kw):
        self.app.autor.value, self.app.titulo.value = autor, titulo
        for k, v in kw.items():
            getattr(self.app, k).value = v

    def test_machado_de_assis(self):
        self.preencher("Machado de Assis", "Dom Casmurro", classe="869.3", ano="1899")
        self.app.gerar()
        self.assertTrue(self.app.painel_resultado.visible)
        self.assertFalse(self.app.painel_erro.visible)
        self.assertEqual(self.app.ultimo.cutter, "As848d")
        t = textos(self.app.painel_resultado)
        self.assertIn("As848d", t)
        self.assertIn("869.3 As848d 1899", t)

    def test_historico_registra_e_persiste(self):
        self.preencher("Machado de Assis", "Dom Casmurro")
        self.app.gerar()
        self.assertEqual(len(self.app.estado["historico"]), 1)
        self.assertTrue(os.path.exists(app_flet.ARQ_ESTADO))
        self.assertEqual(app_flet.carregar_estado()["historico"][0]["cutter"], "As848d")
        self.assertIn("Histórico (1)", self.app.titulo_historico.value)

    def test_campo_vazio(self):
        self.preencher("   ")
        self.app.gerar()
        self.assertTrue(self.app.painel_erro.visible)
        self.assertFalse(self.app.painel_resultado.visible)

    def test_titulo_numerico_mostra_erro(self):
        self.preencher("Assis", "1984")
        self.app.gerar()
        self.assertTrue(self.app.painel_erro.visible)
        self.assertTrue(any("por extenso" in t for t in textos(self.app.painel_erro)))

    def test_mudar_tipo(self):
        self.app.tipo.selected = ["titulo"]
        self.app.mudou_tipo(None)
        self.assertFalse(self.app.titulo.visible)
        self.assertEqual(self.app.autor.label, app_flet.TIPOS["titulo"][0])
        self.preencher("Os Lusíadas")
        self.app.gerar()
        self.assertEqual(self.app.ultimo.marca, "")
        self.app.tipo.selected = ["pessoa"]
        self.app.mudou_tipo(None)
        self.assertTrue(self.app.titulo.visible)

    def test_entidade(self):
        self.app.tipo.selected = ["entidade"]
        self.preencher("Universidade de São Paulo")
        self.app.gerar()
        self.assertEqual(self.app.ultimo.chave, "Universidade")

    def test_letras_da_marca(self):
        self.preencher("Machado de Assis", "Memórias póstumas", letras="2")
        self.app.gerar()
        self.assertEqual(self.app.ultimo.marca, "me")

    def test_aviso_de_entrada_suspeita_aparece_na_tela(self):
        self.preencher("Rungo", "Livro")
        self.app.gerar()
        self.assertTrue(any("inconsistência" in t for t in textos(self.app.painel_resultado)))

    def test_limpar(self):
        self.preencher("Machado de Assis", "Dom Casmurro")
        self.app.gerar()
        self.app.limpar()
        self.assertEqual(self.app.autor.value, "")
        self.assertFalse(self.app.painel_resultado.visible)


class TestTabelaEAjustes(Base):
    def test_consulta_mostra_vizinhanca(self):
        self.app.busca.value = "Adams, John"
        self.app.consultar_tabela()
        tabela = [c for c in self.app.resultado_busca.controls if isinstance(c, ft.DataTable)][0]
        self.assertEqual(len(tabela.rows), 11)
        destacadas = [r for r in tabela.rows if r.color]
        self.assertEqual(len(destacadas), 1)
        self.assertEqual(destacadas[0].cells[1].content.value, "Adams,J.")

    def test_consulta_vazia_limpa(self):
        self.app.busca.value = ""
        self.app.consultar_tabela()
        self.assertEqual(self.app.resultado_busca.controls, [])

    def test_ajuste_prenome_altera_resultado(self):
        self.app.autor.value = "Adams, John"
        self.app.gerar()
        self.assertEqual(self.app.ultimo.codigo, "214")
        # simula o Switch "Usar o prenome" desligado
        aba = self.app.aba_ajustes
        switches = []

        def achar(c):
            if isinstance(c, ft.Switch):
                switches.append(c)
            for nome in ("content", "controls"):
                f = getattr(c, nome, None)
                if isinstance(f, ft.Control):
                    achar(f)
                elif isinstance(f, list):
                    for x in f:
                        achar(x)
        achar(aba)
        prenome = [s for s in switches if "prenome" in s.label][0]
        prenome.value = False
        prenome.on_change(SimpleNamespace(control=prenome))
        self.app.gerar()
        self.assertEqual(self.app.ultimo.codigo, "211")
        self.assertFalse(app_flet.carregar_estado()["ajustes"]["prenome"])

    def test_tema(self):
        self.app.page.theme_mode = ft.ThemeMode.LIGHT
        self.app.alternar_tema()
        self.assertEqual(self.app.page.theme_mode, ft.ThemeMode.DARK)
        self.assertEqual(app_flet.carregar_estado()["tema"], "dark")


class TestClipboard(Base):
    def test_copiar(self):
        copiados = []

        class ClipFalso:
            async def set(self, v):
                copiados.append(v)

        self.app.clip = ClipFalso()
        asyncio.run(self.app.copiar("As848d", "Notação"))
        self.assertEqual(copiados, ["As848d"])
        self.assertEqual(len(self.page.dialogos), 1)


if __name__ == "__main__":
    unittest.main()
