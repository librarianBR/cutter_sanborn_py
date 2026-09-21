#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de notação de autor Cutter-Sanborn (Three-Figure Author Table,
revisão Swanson-Swift, 1969) — offline, adaptado ao português do Brasil.
Depende apenas da biblioteca padrão do Python (3.8+).

ARQUIVOS
--------
tablacutter.json    Tabela: lista de pares [código, chave]. Não é alterada.
correcoes.json      (opcional) Correções que VOCÊ confirmou na edição impressa.
                    Veja "CORREÇÕES" abaixo e correcoes.exemplo.json.

COMO A TABELA FUNCIONA (conforme o arquivo e a lógica do repositório de origem)
-------------------------------------------------------------------------------
1. As chaves são sensíveis a maiúsculas/minúsculas e ordenadas por comparação
   exata de caracteres. Maiúscula no meio da chave marca fronteira de palavra:
   "SanF" (San Fernando) precede "Sanb" e é diferente de "Sanf" (Sanford).
2. O nome é convertido à forma da tabela (sem acentos, cada palavra com inicial
   maiúscula, palavras coladas): "San Francisco" -> "SanFrancisco".
3. Usa-se a última entrada da tabela cuja chave é menor ou igual à do nome
   (se o nome não consta, vale o nome que o precede).
4. Sobrenomes comuns têm entradas com inicial do prenome ("Adams,J."); por isso
   a chave inclui o prenome quando há: "Adams, John" -> "Adams,John".
5. Prefixo da notação: vogal ou S = 2 primeiras letras (Ad211, Sm...);
   Sc = 3 letras (Sch349); demais consoantes = 1 letra (B111).
6. Marca de obra: 1ª letra do título (minúscula), sem o artigo inicial.

O que NÃO vem do repositório e é configurável abaixo (confira na sua edição
impressa): Mc/M' = Mac, St. = Saint, trema alemão = ae/oe/ue, uso do prenome.

ADAPTAÇÕES PARA O PORTUGUÊS DO BRASIL
-------------------------------------
- Elemento de entrada = último sobrenome ("Machado de Assis" -> Assis), exceto
  sobrenomes compostos (Castelo Branco, Espírito Santo, Santa/São...) e nomes
  com qualificador (Filho, Júnior, Neto, Sobrinho, Segundo...), que formam um
  só elemento ("Silva Neto"). Na dúvida, use a forma invertida com vírgula:
  "Rosa, João Guimarães".
- Preposições iniciais (de, da, do, das, dos) são desprezadas.
- Acentos, cedilha e til não afetam a busca.
- Artigos iniciais de títulos (pt, en, es, fr, it, de) são desprezados.

CORREÇÕES (correcoes.json)
--------------------------
Lista de operações, aplicadas sobre a tabela em memória (o JSON original não
é modificado). Cada item tem "chave" e UMA destas ações:
    {"chave": "Fel", "remover": true}
    {"chave": "Berh", "codigo": "499"}
    {"chave": "Henry.G.", "nova_chave": "Henry,G."}
    {"adicionar": {"chave": "XYZ", "codigo": "123"}}
O campo "obs" é livre. Use --validar para ver os defeitos conhecidos.

USO
---
    python cutter_sanborn.py "Machado de Assis" "Dom Casmurro" --classe 869.3 --ano 1899
    python cutter_sanborn.py "Adams, John" "Mistress Masham"
    python cutter_sanborn.py --tipo entidade "Universidade de São Paulo"
    python cutter_sanborn.py --tipo titulo "Os Lusíadas"
    python cutter_sanborn.py                     # modo interativo
    python cutter_sanborn.py --validar           # relatório de integridade da tabela
    python cutter_sanborn.py --exportar-csv tabela.csv
"""

from __future__ import annotations

import argparse
import bisect
import csv
import itertools
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

DIR = Path(__file__).resolve().parent
TABELA_PADRAO = DIR / "tablacutter.json"
CORRECOES_PADRAO = DIR / "correcoes.json"

# ----------------------------------------------------------------------------
# CONFIGURAÇÃO — regras que não constam no repositório de origem.
# Ajuste conforme as instruções da sua edição impressa.
# ----------------------------------------------------------------------------
TRATAR_MC_COMO_MAC = True        # Mc, M' -> Mac
TRATAR_ST_COMO_SAINT = True      # St., St -> Saint
UMLAUT_COMO_DIGRAFO = True       # ä ö ü -> ae oe ue (False: apenas remove o trema)
USAR_PRENOME = True              # inclui o prenome na chave ("Adams,John")

# ----------------------------------------------------------------------------
# Regras linguísticas
# ----------------------------------------------------------------------------

ARTIGOS = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas",                # pt
    "the", "an",                                                     # en
    "el", "la", "los", "las", "un", "una", "unos", "unas", "lo",     # es
    "le", "les", "l", "une",                                         # fr
    "il", "gli", "i", "uno",                                         # it
    "der", "die", "das", "ein", "eine",                              # de
}
PREPOSICOES_PT = {"de", "da", "do", "das", "dos"}
QUALIFICADORES = {
    "filho", "filha", "junior", "jr", "neto", "neta",
    "sobrinho", "sobrinha", "segundo", "bisneto", "bisneta",
}
INICIO_COMPOSTO = {"castelo", "espirito", "santa", "santo", "sao"}

_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
_OUTROS = str.maketrans({
    "ß": "ss", "æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe",
    "ø": "o", "Ø": "O", "đ": "d", "ł": "l", "Ł": "L",
})


def sem_diacriticos(texto: str) -> str:
    if UMLAUT_COMO_DIGRAFO:
        texto = texto.translate(_UMLAUT)
    texto = texto.translate(_OUTROS)
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def _min(p: str) -> str:
    """Palavra em minúsculas, sem acentos e sem pontuação final (para comparar)."""
    return re.sub(r"[^a-z]", "", sem_diacriticos(p).lower())


def _titulo(p: str) -> str:
    return p[:1].upper() + p[1:].lower()


def _palavras(texto: str) -> list[str]:
    return re.findall(r"[^\W_]+", texto, flags=re.UNICODE)


# ----------------------------------------------------------------------------
# Nome -> chave da tabela
# ----------------------------------------------------------------------------

def dividir_nome(nome: str) -> tuple[str, str]:
    """Devolve (elemento_de_entrada, primeiro_prenome). Aceita "Sobrenome, Prenomes"
    ou a ordem direta "Prenomes Sobrenome"."""
    nome = nome.strip()
    if not nome:
        raise ValueError("Nome do autor vazio.")

    if "," in nome:
        elemento, resto = (s.strip() for s in nome.split(",", 1))
        tokens = resto.split()
        prenome = tokens[0] if tokens else ""
    else:
        palavras = nome.split()
        n = 1
        if len(palavras) >= 2:
            if _min(palavras[-1]) in QUALIFICADORES:
                n = 2                                   # Silva Neto
            elif _min(palavras[-2]) in INICIO_COMPOSTO:
                n = 2                                   # Castelo Branco
        elemento = " ".join(palavras[-n:])
        prenome = palavras[0] if len(palavras) > n else ""

    partes = elemento.split()
    while len(partes) > 1 and _min(partes[0]) in PREPOSICOES_PT:   # "de Assis" -> "Assis"
        partes.pop(0)
    return " ".join(partes), prenome


def chave_elemento(elemento: str) -> str:
    """Forma da tabela para o sobrenome/palavra: 'San Francisco' -> 'SanFrancisco'."""
    e = elemento.strip()
    if TRATAR_MC_COMO_MAC:
        e = re.sub(r"^(?:[Mm][Cc]|[Mm]['’])\s*(?=\w)", "Mac", e)
    if TRATAR_ST_COMO_SAINT:
        e = re.sub(r"^[Ss][Tt]\.?\s+", "Saint ", e)
    e = sem_diacriticos(e)
    palavras = [re.sub(r"[^A-Za-z]", "", p) for p in re.split(r"[\s\-'’]+", e)]
    palavras = [p for p in palavras if p]
    if not palavras:
        raise ValueError(
            f"'{elemento}' não contém letras. Escreva números por extenso "
            "(ex.: 1984 -> 'mil novecentos e oitenta e quatro')."
        )
    return "".join(_titulo(p) for p in palavras)


def chave_prenome(prenome: str) -> str:
    """'John' -> 'John'; 'J.' ou 'J' -> 'J.' (a tabela usa a inicial: 'Adams,J.')."""
    tokens = sem_diacriticos(prenome.strip()).split()
    if not tokens:
        return ""
    tok = re.split(r"[-'’]", tokens[0])[0]
    tok = re.sub(r"[^A-Za-z.]", "", tok)
    if not re.search(r"[A-Za-z]", tok):
        return ""
    if "." in tok or len(tok) == 1:                       # inicial(is): J., J.K.
        return tok[0].upper() + "."
    return _titulo(tok)


def chave_tabela(elemento: str, prenome: str = "") -> str:
    chave = chave_elemento(elemento)
    if USAR_PRENOME:
        pn = chave_prenome(prenome)
        if pn:
            chave += "," + pn
    return chave


def primeira_palavra_significativa(texto: str) -> str:
    palavras = _palavras(texto)
    if not palavras:
        raise ValueError("Texto vazio.")
    for p in palavras:
        if _min(p) not in ARTIGOS and _min(p) not in PREPOSICOES_PT:
            return p
    return palavras[0]


def prefixo(chave: str) -> str:
    """Vogal ou S: 2 letras; Sc: 3 letras; demais consoantes: 1 letra."""
    primeira = chave[0].upper()
    if primeira in "AEIOU":
        n = 2
    elif primeira == "S":
        n = 3 if chave[1:2].lower() == "c" else 2
    else:
        n = 1
    return primeira + chave[1:n].lower()


def marca_de_obra(titulo: str, letras: int = 1) -> str:
    palavra = re.sub(r"[^a-z]", "", sem_diacriticos(primeira_palavra_significativa(titulo)).lower())
    if not palavra:
        raise ValueError(
            "O título não começa por letra. Escreva números por extenso "
            "(ex.: 1984 -> 'mil novecentos e oitenta e quatro')."
        )
    return palavra[:max(1, letras)]


# ----------------------------------------------------------------------------
# Tabela: carga, correções e validação
# ----------------------------------------------------------------------------

@dataclass
class Tabela:
    chaves: list[str]
    codigos: list[str]
    problemas: dict[str, list[str]] = field(default_factory=dict)
    correcoes_aplicadas: list[str] = field(default_factory=list)
    origem: str = ""


def validar(chaves: list[str], codigos: list[str]) -> dict[str, list[str]]:
    """Verifica ordenação, largura, monotonicidade, repetição e lacunas dos códigos.
    Devolve {chave: [motivos]} para as entradas envolvidas em cada defeito."""
    probs: dict[str, list[str]] = defaultdict(list)

    def marcar(chave: str, motivo: str) -> None:
        if motivo not in probs[chave]:
            probs[chave].append(motivo)

    for a, b in zip(chaves, chaves[1:]):
        if a > b:
            marcar(a, f"fora de ordem alfabética (antes de '{b}')")
            marcar(b, f"fora de ordem alfabética (depois de '{a}')")

    por_letra: dict[str, list[int]] = defaultdict(list)
    for i, k in enumerate(chaves):
        por_letra[k[0].upper()].append(i)

    for letra, idxs in por_letra.items():
        largura = Counter(len(codigos[i]) for i in idxs).most_common(1)[0][0]
        esperado = {"".join(p) for p in itertools.product("123456789", repeat=largura)}
        validos = []
        for i in idxs:
            c = codigos[i]
            if len(c) != largura or not set(c) <= set("123456789"):
                marcar(chaves[i], f"código '{c}' fora do padrão de {largura} algarismo(s) da letra {letra}")
            else:
                validos.append(i)

        for a, b in zip(validos, validos[1:]):
            if codigos[a] > codigos[b]:
                marcar(chaves[a], f"código {codigos[a]} maior que o da entrada seguinte ('{chaves[b]}' {codigos[b]})")
                marcar(chaves[b], f"código {codigos[b]} menor que o da entrada anterior ('{chaves[a]}' {codigos[a]})")

        repetidos = [c for c, n in Counter(codigos[i] for i in validos).items() if n > 1]
        for c in repetidos:
            for i in validos:
                if codigos[i] == c:
                    marcar(chaves[i], f"código {c} repetido na letra {letra}")

        presentes = {codigos[i] for i in validos}
        for falta in sorted(esperado - presentes):
            anteriores = [i for i in validos if codigos[i] < falta]
            if anteriores:
                ref = max(anteriores, key=lambda i: codigos[i])
                marcar(chaves[ref], f"falta o código {falta} logo após esta entrada")
            elif validos:
                marcar(chaves[validos[0]], f"falta o código {falta} antes desta entrada")
    return dict(probs)


def aplicar_correcoes(entradas: dict[str, str], correcoes: list[dict]) -> list[str]:
    log: list[str] = []
    for n, c in enumerate(correcoes, 1):
        if "adicionar" in c:
            novo = c["adicionar"]
            k, cod = novo["chave"], str(novo["codigo"])
            if k in entradas:
                raise ValueError(f"Correção {n}: a chave '{k}' já existe.")
            entradas[k] = cod
            log.append(f"adicionada '{k}' = {cod}")
            continue
        k = c.get("chave")
        if k not in entradas:
            raise ValueError(f"Correção {n}: chave '{k}' não encontrada na tabela.")
        if c.get("remover"):
            del entradas[k]
            log.append(f"removida '{k}'")
            continue
        if "codigo" in c:
            log.append(f"'{k}': código {entradas[k]} -> {c['codigo']}")
            entradas[k] = str(c["codigo"])
        if "nova_chave" in c:
            nk = c["nova_chave"]
            if nk in entradas and nk != k:
                raise ValueError(f"Correção {n}: a chave '{nk}' já existe.")
            entradas[nk] = entradas.pop(k)
            log.append(f"chave '{k}' -> '{nk}'")
    return log


def carregar_tabela(caminho: Path = TABELA_PADRAO, correcoes: Path | None = CORRECOES_PADRAO) -> Tabela:
    if not caminho.exists():
        raise FileNotFoundError(f"Tabela não encontrada: {caminho}")
    with open(caminho, encoding="utf-8") as f:
        bruto = json.load(f)

    if not isinstance(bruto, list) or not bruto:
        raise ValueError("tablacutter.json deve ser uma lista não vazia de pares [código, chave].")
    entradas: dict[str, str] = {}
    for i, par in enumerate(bruto):
        if not (isinstance(par, list) and len(par) == 2 and all(isinstance(x, str) for x in par)):
            raise ValueError(f"Entrada {i} inválida: {par!r}")
        codigo, chave = par
        if not chave or not chave[0].isalpha():
            raise ValueError(f"Entrada {i}: chave inválida {chave!r}")
        if chave in entradas:
            raise ValueError(f"Chave duplicada na tabela: {chave!r}")
        entradas[chave] = codigo

    log: list[str] = []
    if correcoes and correcoes.exists():
        with open(correcoes, encoding="utf-8") as f:
            lista = json.load(f)
        if lista:
            log = aplicar_correcoes(entradas, lista)

    chaves = sorted(entradas)                                 # ordem exata de caracteres
    codigos = [entradas[k] for k in chaves]
    return Tabela(chaves, codigos, validar(chaves, codigos), log, str(caminho))


def buscar(tabela: Tabela, chave: str) -> tuple[int, bool, str | None]:
    """Última entrada com chave <= alvo. Devolve (índice, exata, aviso)."""
    i = bisect.bisect_right(tabela.chaves, chave) - 1
    if i < 0 or tabela.chaves[i][0] != chave[0]:
        j = bisect.bisect_left(tabela.chaves, chave[0])
        if j < len(tabela.chaves) and tabela.chaves[j][0] == chave[0]:
            return j, False, "O nome antecede a 1ª entrada da sua letra; usada a primeira entrada dela."
        raise LookupError(f"A tabela não possui entradas iniciadas por '{chave[0]}'.")
    return i, tabela.chaves[i] == chave, None


# ----------------------------------------------------------------------------
# Geração da notação
# ----------------------------------------------------------------------------

@dataclass
class Resultado:
    cutter: str
    prefixo: str
    codigo: str
    marca: str
    elemento: str
    chave: str
    entrada_tabela: str
    exata: bool
    etiqueta: list[str]
    chamada: str
    avisos: list[str]


def gerar_cutter(
    autor: str,
    titulo: str = "",
    *,
    tabela: Tabela,
    tipo: str = "pessoa",            # pessoa | entidade | titulo
    classe: str = "",
    ano: str = "",
    volume: str = "",
    exemplar: str = "",
    letras_marca: int = 1,
) -> Resultado:
    if tipo == "pessoa":
        elemento, prenome = dividir_nome(autor)
        chave = chave_tabela(elemento, prenome)
    elif tipo in ("entidade", "titulo"):
        # Entidade coletiva ou obra sem autor: 1ª palavra significativa (sem artigo)
        elemento = autor.strip()
        chave = chave_tabela(primeira_palavra_significativa(autor))
    else:
        raise ValueError("tipo deve ser: pessoa, entidade ou titulo")

    i, exata, aviso = buscar(tabela, chave)
    avisos = [aviso] if aviso else []
    entrada = tabela.chaves[i]
    if entrada in tabela.problemas:
        avisos.append(
            f"A entrada da tabela '{entrada}' tem inconsistência conhecida "
            f"({'; '.join(tabela.problemas[entrada])}). Confira na edição impressa."
        )

    codigo = tabela.codigos[i]
    pref = prefixo(chave)
    marca = marca_de_obra(titulo, letras_marca) if (tipo != "titulo" and titulo.strip()) else ""
    cutter = f"{pref}{codigo}{marca}"

    etiqueta = [p for p in (classe, cutter, ano,
                            f"v.{volume}" if volume else "",
                            f"ex.{exemplar}" if exemplar else "") if p]
    return Resultado(cutter, pref, codigo, marca, elemento, chave, entrada, exata,
                     etiqueta, " ".join(etiqueta), avisos)


# ----------------------------------------------------------------------------
# Interface de linha de comando
# ----------------------------------------------------------------------------

def imprimir(r: Resultado) -> None:
    print(f"Elemento de entrada : {r.elemento}")
    print(f"Chave de busca      : {r.chave}")
    como = "exata" if r.exata else "entrada anterior na tabela"
    print(f"Entrada da tabela   : {r.entrada_tabela} -> {r.codigo} ({como})")
    print(f"Notação Cutter      : {r.cutter}")
    print("\nEtiqueta de lombada:")
    for linha in r.etiqueta:
        print(f"  {linha}")
    print(f"\nNº de chamada       : {r.chamada}")
    for a in r.avisos:
        print(f"\n[AVISO] {a}")


def relatorio_validacao(tabela: Tabela) -> None:
    print(f"Tabela: {tabela.origem}")
    print(f"Entradas: {len(tabela.chaves)}")
    if tabela.correcoes_aplicadas:
        print(f"\nCorreções aplicadas ({len(tabela.correcoes_aplicadas)}):")
        for c in tabela.correcoes_aplicadas:
            print(f"  - {c}")
    else:
        print("Correções aplicadas: nenhuma (tabela original).")
    if not tabela.problemas:
        print("\nNenhuma inconsistência encontrada.")
        return
    print(f"\nInconsistências ({len(tabela.problemas)} entradas) — confira na edição impressa:")
    for chave in sorted(tabela.problemas):
        for motivo in tabela.problemas[chave]:
            print(f"  {chave:<16} {motivo}")


def exportar_csv(tabela: Tabela, destino: Path) -> None:
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["codigo", "chave", "observacao"])
        for k, c in zip(tabela.chaves, tabela.codigos):
            w.writerow([c, k, "; ".join(tabela.problemas.get(k, []))])
    print(f"{len(tabela.chaves)} linhas gravadas em {destino}")
    print("Atenção: este CSV é só para conferência. Não reordene em planilha "
          "(a ordem exata, com diferença entre maiúsculas e minúsculas, é essencial).")


def modo_interativo(tabela: Tabela) -> None:
    print("Cutter-Sanborn (Swanson-Swift 1969) — Ctrl+C para sair.\n")
    try:
        while True:
            tipo = input("Tipo [pessoa/entidade/titulo] (Enter=pessoa): ").strip() or "pessoa"
            autor = input("Autor (ou título, se tipo=titulo): ").strip()
            titulo = "" if tipo == "titulo" else input("Título da obra: ").strip()
            classe = input("Classe CDD/CDU (opcional): ").strip()
            ano = input("Ano (opcional): ").strip()
            volume = input("Volume (opcional): ").strip()
            exemplar = input("Exemplar (opcional): ").strip()
            print()
            try:
                imprimir(gerar_cutter(autor, titulo, tabela=tabela, tipo=tipo, classe=classe,
                                      ano=ano, volume=volume, exemplar=exemplar))
            except (ValueError, LookupError) as e:
                print(f"Erro: {e}")
            print("\n" + "-" * 50 + "\n")
    except (KeyboardInterrupt, EOFError):
        print("\nAté logo!")


def main() -> int:
    global USAR_PRENOME
    ap = argparse.ArgumentParser(description="Gerador Cutter-Sanborn (offline, pt-BR)")
    ap.add_argument("autor", nargs="?", help='Ex.: "Machado de Assis" ou "Assis, Machado de"')
    ap.add_argument("titulo", nargs="?", default="", help="Título da obra")
    ap.add_argument("--tipo", choices=["pessoa", "entidade", "titulo"], default="pessoa")
    ap.add_argument("--tabela", type=Path, default=TABELA_PADRAO, help="JSON da tabela")
    ap.add_argument("--correcoes", type=Path, default=CORRECOES_PADRAO, help="JSON de correções")
    ap.add_argument("--sem-correcoes", action="store_true", help="Ignora o arquivo de correções")
    ap.add_argument("--sem-prenome", action="store_true", help="Não usa o prenome na chave")
    ap.add_argument("--classe", default="", help="Número de classificação (CDD/CDU)")
    ap.add_argument("--ano", default="")
    ap.add_argument("--volume", default="")
    ap.add_argument("--exemplar", default="")
    ap.add_argument("--letras-marca", type=int, default=1,
                    help="Nº de letras da marca de obra (2+ para distinguir obras do mesmo autor)")
    ap.add_argument("--validar", action="store_true", help="Relatório de integridade da tabela")
    ap.add_argument("--exportar-csv", type=Path, metavar="ARQUIVO", help="Exporta a tabela em CSV (conferência)")
    args = ap.parse_args()

    if args.sem_prenome:
        USAR_PRENOME = False

    try:
        tabela = carregar_tabela(args.tabela, None if args.sem_correcoes else args.correcoes)
        if args.validar:
            relatorio_validacao(tabela)
            return 0
        if args.exportar_csv:
            exportar_csv(tabela, args.exportar_csv)
            return 0
        if not args.autor:
            modo_interativo(tabela)
            return 0
        imprimir(gerar_cutter(
            args.autor, args.titulo, tabela=tabela, tipo=args.tipo, classe=args.classe,
            ano=args.ano, volume=args.volume, exemplar=args.exemplar,
            letras_marca=args.letras_marca))
    except (FileNotFoundError, ValueError, LookupError, json.JSONDecodeError) as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:          # ex.: python cutter_sanborn.py --validar | head
        sys.exit(0)
