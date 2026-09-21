#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface gráfica (Flet 1.0) do gerador Cutter-Sanborn — Swanson-Swift, 1969.

Requer os arquivos cutter_sanborn.py, tablacutter.json e correcoes.json na mesma
pasta. Toda a lógica de catalogação está em cutter_sanborn.py; este arquivo
só cuida da interface.

Instalação (uma vez):   pip install -r requirements.txt

Execução:
    python app_flet.py            # janela de desktop
    python app_flet.py --web      # abre no navegador local (100% offline)

Offline:
  * --web  funciona sem internet desde a instalação: o pacote flet-web já traz o
    cliente completo (CanvasKit, fontes e ícones) e o app roda com no_cdn=True.
  * janela de desktop: o pacote flet-desktop baixa o cliente gráfico do GitHub
    na PRIMEIRA execução e o guarda em ~/.flet/client. Depois disso não precisa
    de internet. Para instalar sem internet, veja o LEIA-ME.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import flet as ft

import cutter_sanborn as cs

TITULO_APP = "Cutter-Sanborn · Swanson-Swift 1969"
MAX_HISTORICO = 200
PASTA_ESTADO = Path(os.environ.get("CUTTER_SANBORN_HOME", Path.home() / ".cutter_sanborn"))
ARQ_ESTADO = PASTA_ESTADO / "estado.json"

AJUSTES_PADRAO = {"mc": True, "st": True, "trema": True, "prenome": True}
TIPOS = {
    "pessoa": ("Autor (pessoa)", "Machado de Assis   ou   Assis, Machado de"),
    "entidade": ("Entidade / autor coletivo", "Universidade de São Paulo"),
    "titulo": ("Título (obra sem autor)", "Os Lusíadas"),
}
MONO = "Courier New"


# ----------------------------------------------------------------------------
# Estado do usuário (histórico e ajustes), guardado em ~/.cutter_sanborn
# ----------------------------------------------------------------------------

def carregar_estado() -> dict:
    try:
        with open(ARQ_ESTADO, encoding="utf-8") as f:
            e = json.load(f)
        if not isinstance(e, dict):
            raise ValueError
    except (OSError, ValueError):
        e = {}
    e["ajustes"] = {**AJUSTES_PADRAO, **{k: v for k, v in e.get("ajustes", {}).items() if k in AJUSTES_PADRAO}}
    e["historico"] = [h for h in e.get("historico", []) if isinstance(h, dict)][:MAX_HISTORICO]
    e["tema"] = e.get("tema") if e.get("tema") in ("light", "dark", "system") else "system"
    return e


def salvar_estado(estado: dict) -> None:
    try:
        PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
        with open(ARQ_ESTADO, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=1)
    except OSError:
        pass                                   # histórico é conveniência; não derruba o app


def aplicar_ajustes(a: dict) -> None:
    cs.TRATAR_MC_COMO_MAC = bool(a["mc"])
    cs.TRATAR_ST_COMO_SAINT = bool(a["st"])
    cs.UMLAUT_COMO_DIGRAFO = bool(a["trema"])
    cs.USAR_PRENOME = bool(a["prenome"])


# ----------------------------------------------------------------------------
# Aplicativo
# ----------------------------------------------------------------------------

class CutterApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.estado = carregar_estado()
        aplicar_ajustes(self.estado["ajustes"])
        self.tabela: cs.Tabela | None = None
        self.erro_tabela = ""
        self.ultimo: cs.Resultado | None = None
        self.clip = ft.Clipboard()

    # ---------------------------------------------------------------- utilidades
    def carregar_tabela(self) -> None:
        try:
            self.tabela = cs.carregar_tabela(cs.TABELA_PADRAO, cs.CORRECOES_PADRAO)
            self.erro_tabela = ""
        except (OSError, ValueError, LookupError) as e:
            self.tabela = None
            self.erro_tabela = str(e)

    async def copiar(self, texto: str, rotulo: str = "Texto") -> None:
        await self.clip.set(texto)
        self.page.show_dialog(ft.SnackBar(content=ft.Text(f"{rotulo} copiado."), duration=1600))

    def botao_copiar(self, texto: str, rotulo: str, dica: str = "Copiar") -> ft.IconButton:
        async def ao_clicar(e):
            await self.copiar(texto, rotulo)
        return ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip=dica, on_click=ao_clicar)

    # ---------------------------------------------------------------- montagem
    def montar(self) -> None:
        p = self.page
        p.title = TITULO_APP
        p.padding = 0
        p.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
        p.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
        p.theme_mode = {"light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}.get(
            self.estado["tema"], ft.ThemeMode.SYSTEM)
        try:
            p.window.width, p.window.height = 1000, 780
            p.window.min_width, p.window.min_height = 640, 560
        except AttributeError:
            pass
        p.services.append(self.clip)

        self.carregar_tabela()
        self.btn_tema = ft.IconButton(icon=self._icone_tema(), tooltip="Alternar tema", on_click=self.alternar_tema)
        p.appbar = ft.AppBar(
            title=ft.Text(TITULO_APP, size=18, weight=ft.FontWeight.W_600),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            actions=[self.btn_tema, ft.Container(width=8)],
        )

        if self.tabela is None:
            p.add(ft.Container(
                padding=24, expand=True,
                content=ft.Column(spacing=12, controls=[
                    ft.Row([ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR),
                            ft.Text("Não foi possível carregar a tabela.", size=20, weight=ft.FontWeight.BOLD)]),
                    ft.Text(self.erro_tabela, selectable=True),
                    ft.Text("Confira se tablacutter.json e correcoes.json estão na mesma pasta do programa "
                            "e se são JSON válidos."),
                ])))
            return

        self.aba_gerar = self._montar_aba_gerar()
        self.aba_historico = self._montar_aba_historico()
        self.aba_tabela = self._montar_aba_tabela()
        self.aba_ajustes = self._montar_aba_ajustes()

        def aba(icone, texto):
            return ft.Tab(label=texto, icon=icone)

        p.add(ft.Tabs(
            length=4, selected_index=0, expand=True,
            content=ft.Column(expand=True, spacing=0, controls=[
                ft.TabBar(tabs=[
                    aba(ft.Icons.EDIT_NOTE, "Gerar"),
                    aba(ft.Icons.HISTORY, "Histórico"),
                    aba(ft.Icons.TABLE_ROWS, "Tabela"),
                    aba(ft.Icons.TUNE, "Ajustes"),
                ]),
                ft.TabBarView(expand=True, controls=[
                    self.aba_gerar, self.aba_historico, self.aba_tabela, self.aba_ajustes,
                ]),
            ])))
        self.atualizar_historico()
        self.mostrar_integridade()

    def _rolavel(self, *controles: ft.Control) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.all(20), expand=True,
            content=ft.Column(controls=list(controles), spacing=14, scroll=ft.ScrollMode.AUTO, expand=True))

    # ---------------------------------------------------------------- aba Gerar
    def _montar_aba_gerar(self) -> ft.Control:
        self.tipo = ft.SegmentedButton(
            selected=["pessoa"], allow_empty_selection=False, on_change=self.mudou_tipo,
            segments=[
                ft.Segment(value="pessoa", label=ft.Text("Pessoa"), icon=ft.Icon(ft.Icons.PERSON)),
                ft.Segment(value="entidade", label=ft.Text("Entidade"), icon=ft.Icon(ft.Icons.BUSINESS)),
                ft.Segment(value="titulo", label=ft.Text("Título (sem autor)"), icon=ft.Icon(ft.Icons.TITLE)),
            ])
        self.autor = ft.TextField(label=TIPOS["pessoa"][0], hint_text=TIPOS["pessoa"][1],
                                  autofocus=True, on_submit=self.gerar)
        self.titulo = ft.TextField(label="Título da obra (define a marca de obra)", on_submit=self.gerar)
        self.classe = ft.TextField(label="Classe (CDD/CDU)", width=170, on_submit=self.gerar)
        self.ano = ft.TextField(label="Ano", width=100, on_submit=self.gerar)
        self.volume = ft.TextField(label="Volume", width=100, on_submit=self.gerar)
        self.exemplar = ft.TextField(label="Exemplar", width=110, on_submit=self.gerar)
        self.letras = ft.Dropdown(
            label="Letras da marca", value="1", width=150,
            options=[ft.DropdownOption(key=k, text=t) for k, t in
                     (("1", "1 letra"), ("2", "2 letras"), ("3", "3 letras"))])

        self.painel_erro = ft.Container(visible=False, padding=12, border_radius=8,
                                        bgcolor=ft.Colors.ERROR_CONTAINER)
        self.painel_resultado = ft.Container(visible=False)

        acoes = ft.Row(spacing=10, controls=[
            ft.FilledButton(content="Gerar notação", icon=ft.Icons.AUTO_FIX_HIGH, on_click=self.gerar),
            ft.TextButton(content="Limpar", icon=ft.Icons.CLEAR, on_click=self.limpar),
        ])
        return self._rolavel(
            self.tipo, self.autor, self.titulo,
            ft.Row(wrap=True, spacing=10, run_spacing=10,
                   controls=[self.classe, self.ano, self.volume, self.exemplar, self.letras]),
            acoes, self.painel_erro, self.painel_resultado)

    def mudou_tipo(self, e) -> None:
        tipo = self.tipo.selected[0]
        self.autor.label, self.autor.hint_text = TIPOS[tipo]
        self.titulo.visible = tipo != "titulo"
        self.page.update()

    def limpar(self, e=None) -> None:
        for c in (self.autor, self.titulo, self.classe, self.ano, self.volume, self.exemplar):
            c.value = ""
        self.painel_erro.visible = False
        self.painel_resultado.visible = False
        self.ultimo = None
        self.page.update()

    def _mostrar_erro(self, texto: str) -> None:
        self.painel_erro.content = ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[
            ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ON_ERROR_CONTAINER),
            ft.Text(texto, color=ft.Colors.ON_ERROR_CONTAINER, expand=True, selectable=True)])
        self.painel_erro.visible = True
        self.painel_resultado.visible = False
        self.page.update()

    def gerar(self, e=None) -> None:
        tipo = self.tipo.selected[0]
        autor = (self.autor.value or "").strip()
        if not autor:
            self._mostrar_erro("Informe o nome do autor, da entidade ou o título.")
            return
        try:
            r = cs.gerar_cutter(
                autor, "" if tipo == "titulo" else (self.titulo.value or ""),
                tabela=self.tabela, tipo=tipo,
                classe=(self.classe.value or "").strip(), ano=(self.ano.value or "").strip(),
                volume=(self.volume.value or "").strip(), exemplar=(self.exemplar.value or "").strip(),
                letras_marca=int(self.letras.value or 1))
        except (ValueError, LookupError) as ex:
            self._mostrar_erro(str(ex))
            return

        self.ultimo = r
        self.painel_erro.visible = False
        self.painel_resultado.content = self._cartao_resultado(r)
        self.painel_resultado.visible = True
        self._registrar(tipo, autor, r)
        self.page.update()

    def _cartao_resultado(self, r: cs.Resultado) -> ft.Control:
        cor_fundo = ft.Colors.SURFACE_CONTAINER_LOW
        lombada = ft.Container(
            width=150, padding=ft.Padding.symmetric(vertical=12, horizontal=10),
            border=ft.Border.all(1, ft.Colors.OUTLINE), border_radius=4, bgcolor=ft.Colors.SURFACE,
            content=ft.Column(spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                ft.Text(l, font_family=MONO, size=16, weight=ft.FontWeight.BOLD if l == r.cutter else None,
                        selectable=True) for l in r.etiqueta]))
        como = "exata" if r.exata else "entrada anterior na tabela"
        detalhes = ft.Column(spacing=4, expand=True, controls=[
            ft.Text("Nº de chamada", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row(controls=[ft.Text(r.chamada, size=18, font_family=MONO, selectable=True),
                             self.botao_copiar(r.chamada, "Nº de chamada", "Copiar nº de chamada")]),
            ft.Divider(height=8),
            ft.Text(f"Elemento de entrada:  {r.elemento}", selectable=True),
            ft.Text(f"Chave de busca:  {r.chave}", selectable=True),
            ft.Text(f"Entrada da tabela:  {r.entrada_tabela}  →  {r.codigo}   ({como})", selectable=True),
        ])
        topo = ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
            ft.Text(r.cutter, size=44, weight=ft.FontWeight.BOLD, font_family=MONO,
                    color=ft.Colors.PRIMARY, selectable=True),
            self.botao_copiar(r.cutter, "Notação Cutter", "Copiar notação Cutter")])
        avisos = [
            ft.Container(
                padding=10, border_radius=8, bgcolor=ft.Colors.TERTIARY_CONTAINER,
                content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ON_TERTIARY_CONTAINER),
                    ft.Text(a, color=ft.Colors.ON_TERTIARY_CONTAINER, expand=True, selectable=True)]))
            for a in r.avisos]
        return ft.Card(content=ft.Container(padding=18, bgcolor=cor_fundo, border_radius=12, content=ft.Column(
            spacing=12, controls=[
                topo,
                ft.Row(wrap=True, spacing=24, run_spacing=12,
                       vertical_alignment=ft.CrossAxisAlignment.START, controls=[lombada, detalhes]),
                *avisos,
            ])))

    # ---------------------------------------------------------------- histórico
    def _registrar(self, tipo: str, autor: str, r: cs.Resultado) -> None:
        item = {"quando": datetime.now().strftime("%d/%m/%Y %H:%M"), "tipo": tipo, "autor": autor,
                "titulo": (self.titulo.value or "").strip() if tipo != "titulo" else "",
                "cutter": r.cutter, "chamada": r.chamada}
        hist = self.estado["historico"]
        hist.insert(0, item)
        del hist[MAX_HISTORICO:]
        salvar_estado(self.estado)
        self.atualizar_historico()

    def _montar_aba_historico(self) -> ft.Control:
        self.lista_historico = ft.Column(spacing=4)
        self.titulo_historico = ft.Text("", size=16, weight=ft.FontWeight.W_600)

        async def copiar_tudo(e):
            linhas = ["Data\tTipo\tAutor\tTítulo\tCutter\tNº de chamada"] + [
                "\t".join([h.get("quando", ""), h.get("tipo", ""), h.get("autor", ""), h.get("titulo", ""),
                           h.get("cutter", ""), h.get("chamada", "")]) for h in self.estado["historico"]]
            await self.copiar("\n".join(linhas), "Histórico (cole numa planilha)")

        def limpar_tudo(e):
            self.estado["historico"].clear()
            salvar_estado(self.estado)
            self.atualizar_historico()

        barra = ft.Row(wrap=True, spacing=10, controls=[
            self.titulo_historico,
            ft.TextButton(content="Copiar tudo (planilha)", icon=ft.Icons.CONTENT_COPY, on_click=copiar_tudo),
            ft.TextButton(content="Limpar histórico", icon=ft.Icons.DELETE_OUTLINE, on_click=limpar_tudo),
        ])
        return self._rolavel(barra, self.lista_historico)

    def atualizar_historico(self) -> None:
        hist = self.estado["historico"]
        self.titulo_historico.value = f"Histórico ({len(hist)})"
        if not hist:
            self.lista_historico.controls = [ft.Text("Nenhuma notação gerada ainda.",
                                                      color=ft.Colors.ON_SURFACE_VARIANT)]
        else:
            self.lista_historico.controls = [
                ft.ListTile(
                    dense=True,
                    leading=ft.Icon({"pessoa": ft.Icons.PERSON, "entidade": ft.Icons.BUSINESS}.get(
                        h.get("tipo"), ft.Icons.TITLE)),
                    title=ft.Text(h.get("chamada", ""), font_family=MONO, weight=ft.FontWeight.BOLD),
                    subtitle=ft.Text(" · ".join(x for x in (h.get("autor"), h.get("titulo"), h.get("quando")) if x)),
                    trailing=self.botao_copiar(h.get("chamada", ""), "Nº de chamada"))
                for h in hist]
        try:
            self.page.update()
        except Exception:                      # ainda não montado na 1ª chamada
            pass

    # ---------------------------------------------------------------- aba Tabela
    def _montar_aba_tabela(self) -> ft.Control:
        self.busca = ft.TextField(
            label="Consultar a tabela", hint_text="Sobrenome ou 'Sobrenome, Prenome'   (ex.: Adams, John)",
            prefix_icon=ft.Icons.SEARCH, on_change=self.consultar_tabela, on_submit=self.consultar_tabela)
        self.resultado_busca = ft.Column(spacing=6)
        self.resumo_integridade = ft.Text("", size=15, weight=ft.FontWeight.W_600)
        self.lista_integridade = ft.Column(spacing=0)

        async def recarregar(e):
            self.carregar_tabela()
            if self.tabela is None:
                self.page.show_dialog(ft.SnackBar(content=ft.Text(f"Erro: {self.erro_tabela}"), duration=5000))
                return
            self.mostrar_integridade()
            self.consultar_tabela()
            self.page.show_dialog(ft.SnackBar(content=ft.Text("Tabela e correções recarregadas."), duration=2000))

        return self._rolavel(
            self.busca, self.resultado_busca, ft.Divider(),
            ft.Row(wrap=True, controls=[
                ft.Icon(ft.Icons.CHECK_CIRCLE), self.resumo_integridade,
                ft.TextButton(content="Recarregar tabela e correções", icon=ft.Icons.REFRESH, on_click=recarregar)]),
            ft.Text("Entradas com inconsistência conhecida. Confira na edição impressa; "
                    "correções confirmadas vão em correcoes.json.",
                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            self.lista_integridade)

    def consultar_tabela(self, e=None) -> None:
        texto = (self.busca.value or "").strip()
        self.resultado_busca.controls = []
        if texto and self.tabela:
            try:
                elemento, _, prenome = texto.partition(",")
                chave = cs.chave_tabela(elemento, prenome)
                i, exata, aviso = cs.buscar(self.tabela, chave)
                t = self.tabela
                linhas = []
                for j in range(max(0, i - 5), min(len(t.chaves), i + 6)):
                    marcado = j == i
                    problema = t.chaves[j] in t.problemas
                    linhas.append(ft.DataRow(
                        color=ft.Colors.PRIMARY_CONTAINER if marcado else None,
                        cells=[
                            ft.DataCell(ft.Text(t.codigos[j], font_family=MONO,
                                                weight=ft.FontWeight.BOLD if marcado else None)),
                            ft.DataCell(ft.Text(t.chaves[j], font_family=MONO,
                                                weight=ft.FontWeight.BOLD if marcado else None)),
                            ft.DataCell(ft.Icon(ft.Icons.WARNING_AMBER, size=18) if problema else ft.Text("")),
                        ]))
                self.resultado_busca.controls = [
                    ft.Text(f"Chave de busca: {chave}   →   {'entrada exata' if exata else 'entrada anterior'}: "
                            f"{t.chaves[i]} ({t.codigos[i]})", selectable=True),
                    *([ft.Text(aviso, color=ft.Colors.ERROR)] if aviso else []),
                    ft.DataTable(columns=[ft.DataColumn(label=ft.Text("Código")),
                                          ft.DataColumn(label=ft.Text("Chave")),
                                          ft.DataColumn(label=ft.Text(""))],
                                 rows=linhas, data_row_min_height=32, heading_row_height=36),
                ]
            except (ValueError, LookupError) as ex:
                self.resultado_busca.controls = [ft.Text(str(ex), color=ft.Colors.ERROR)]
        self.page.update()

    def mostrar_integridade(self) -> None:
        t = self.tabela
        if t is None:
            return
        n = len(t.problemas)
        self.resumo_integridade.value = (
            f"{len(t.chaves):,} entradas · {n} com inconsistência · "
            f"{len(t.correcoes_aplicadas)} correção(ões) aplicada(s)").replace(",", ".")
        codigo = dict(zip(t.chaves, t.codigos))
        self.lista_integridade.controls = [
            ft.ListTile(dense=True,
                        leading=ft.Icon(ft.Icons.WARNING_AMBER),
                        title=ft.Text(f"{k}   ({codigo.get(k, '?')})", font_family=MONO),
                        subtitle=ft.Text("; ".join(t.problemas[k])))
            for k in sorted(t.problemas)]
        if not n:
            self.lista_integridade.controls = [ft.Text("Nenhuma inconsistência encontrada.")]
        try:
            self.page.update()
        except Exception:
            pass

    # ---------------------------------------------------------------- aba Ajustes
    def _montar_aba_ajustes(self) -> ft.Control:
        def sw(chave, rotulo, ajuda):
            def mudou(e):
                self.estado["ajustes"][chave] = e.control.value
                aplicar_ajustes(self.estado["ajustes"])
                salvar_estado(self.estado)
            return ft.Column(spacing=0, controls=[
                ft.Switch(label=rotulo, value=self.estado["ajustes"][chave], on_change=mudou),
                ft.Text(ajuda, size=12, color=ft.Colors.ON_SURFACE_VARIANT)])

        return self._rolavel(
            ft.Text("Regras que não constam no repositório de origem da tabela", size=16,
                    weight=ft.FontWeight.W_600),
            ft.Text("Confira as instruções da sua edição impressa e ajuste conforme necessário. "
                    "As alterações valem para as próximas notações geradas.",
                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            sw("mc", "Mc e M' tratados como Mac", "McDonald é buscado como MacDonald (letra M)."),
            sw("st", "St. tratado como Saint", "St. Andrew é buscado como Saint Andrew."),
            sw("trema", "Trema alemão como ae / oe / ue", "Müller é buscado como Mueller. Desligado: só remove o trema."),
            sw("prenome", "Usar o prenome na busca",
               "Necessário para as entradas da tabela com inicial do prenome (Adams,J.)."),
            ft.Divider(),
            ft.Text("Arquivos em uso", size=16, weight=ft.FontWeight.W_600),
            ft.Text(f"Tabela:  {cs.TABELA_PADRAO}", selectable=True, size=12),
            ft.Text(f"Correções:  {cs.CORRECOES_PADRAO}", selectable=True, size=12),
            ft.Text(f"Histórico e ajustes:  {ARQ_ESTADO}", selectable=True, size=12),
        )

    # ---------------------------------------------------------------- tema
    def _icone_tema(self):
        return ft.Icons.LIGHT_MODE if self.page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE

    def alternar_tema(self, e=None) -> None:
        escuro = self.page.theme_mode == ft.ThemeMode.DARK
        self.page.theme_mode = ft.ThemeMode.LIGHT if escuro else ft.ThemeMode.DARK
        self.estado["tema"] = "light" if escuro else "dark"
        salvar_estado(self.estado)
        self.btn_tema.icon = self._icone_tema()
        self.page.update()


def main(page: ft.Page) -> None:
    CutterApp(page).montar()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Interface Flet do gerador Cutter-Sanborn")
    ap.add_argument("--web", action="store_true", help="abre no navegador (100%% offline, sem cliente desktop)")
    ap.add_argument("--porta", type=int, default=0, help="porta do servidor local (modo --web)")
    args = ap.parse_args()
    if args.web:
        ft.run(main, view=ft.AppView.WEB_BROWSER, host="127.0.0.1", port=args.porta, no_cdn=True)
    else:
        ft.run(main)
