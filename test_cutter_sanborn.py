import json
import tempfile
import unittest
from pathlib import Path

import cutter_sanborn as cs

TABELA = cs.carregar_tabela(cs.TABELA_PADRAO, None)   # tabela original, sem correções


def cutter(autor, titulo="", **kw):
    return cs.gerar_cutter(autor, titulo, tabela=TABELA, **kw)


class TestTabela(unittest.TestCase):
    def test_carga(self):
        self.assertEqual(len(TABELA.chaves), 12329)
        self.assertEqual((TABELA.chaves[0], TABELA.codigos[0]), ("Aa", "111"))
        self.assertEqual((TABELA.chaves[-1], TABELA.codigos[-1]), ("Zy", "99"))

    def test_ordem_exata(self):
        self.assertEqual(TABELA.chaves, sorted(TABELA.chaves))

    def test_defeitos_conhecidos_sao_detectados(self):
        for chave in ("Fel", "Funn", "Henry.G.", "Berh", "Hoy", "Jeffri", "Rung", "Ryv"):
            self.assertIn(chave, TABELA.problemas, chave)

    def test_correcoes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps([
                {"chave": "Fel", "remover": True},
                {"chave": "Henry.G.", "nova_chave": "Henry,G."},
            ]), encoding="utf-8")
            t = cs.carregar_tabela(cs.TABELA_PADRAO, p)
            self.assertNotIn("Fel", t.chaves)
            self.assertIn("Henry,G.", t.chaves)
            self.assertNotIn("Henry.G.", t.problemas)
            self.assertEqual(t.chaves, sorted(t.chaves))


class TestReferenciasDoRepositorio(unittest.TestCase):
    """Resultados que os testes do repositório de origem esperam."""

    def num(self, texto):
        chave = cs.chave_tabela(texto)
        i, _, _ = cs.buscar(TABELA, chave)
        return cs.prefixo(chave) + TABELA.codigos[i]

    def test_adams(self):
        self.assertEqual(self.num("Adams"), "Ad211")

    def test_schmidt(self):
        self.assertEqual(self.num("Schmidt"), "Sch349")

    def test_fronteira_de_palavra(self):
        self.assertEqual(self.num("San Francisco"), "Sa195")   # SanF
        self.assertEqual(self.num("Sanford"), "Sa224")         # Sanf

    def test_saint(self):
        self.assertEqual(self.num("Saint Andrew"), "Sa134")
        self.assertEqual(self.num("Saint"), "Sa132")

    def test_jimenez(self):
        self.assertEqual(self.num("Jimenez"), "J61")


class TestBrasil(unittest.TestCase):
    def test_machado_de_assis(self):
        r = cutter("Machado de Assis", "Dom Casmurro")
        self.assertEqual(r.elemento, "Assis")
        self.assertEqual(r.cutter, "As848d")

    def test_forma_invertida_igual_a_direta(self):
        a = cutter("Assis, Machado de", "Dom Casmurro").cutter
        b = cutter("Machado de Assis", "Dom Casmurro").cutter
        self.assertEqual(a, b)

    def test_drummond(self):
        r = cutter("Carlos Drummond de Andrade", "A rosa do povo")
        self.assertEqual(r.elemento, "Andrade")
        self.assertEqual(r.cutter, "An553r")

    def test_composto_e_qualificador(self):
        self.assertEqual(cutter("Camilo Castelo Branco", "Amor de perdição").elemento, "Castelo Branco")
        self.assertEqual(cutter("Joaquim da Silva Neto", "Ólá").elemento, "Silva Neto")

    def test_acentos(self):
        self.assertEqual(cutter("João Guimarães Rosa", "Sagarana").cutter,
                         cutter("Joao Guimaraes Rosa", "Sagarana").cutter)

    def test_prenome_usado_quando_a_tabela_tem_inicial(self):
        self.assertEqual(cutter("Adams, John").cutter, "Ad214")      # Adams,J.
        self.assertEqual(cutter("Adams").cutter, "Ad211")

    def test_mc_como_mac(self):
        self.assertEqual(cutter("McDonald").cutter, cutter("MacDonald").cutter)

    def test_titulo_sem_artigo(self):
        self.assertEqual(cutter("Assis", "O alienista").marca, "a")
        self.assertEqual(cutter("Assis", "Os Lusíadas").marca, "l")

    def test_obra_sem_autor_nao_tem_marca(self):
        r = cutter("Os Lusíadas", tipo="titulo")
        self.assertEqual(r.marca, "")
        self.assertTrue(r.cutter.startswith("L"))

    def test_entidade(self):
        r = cutter("Universidade de São Paulo", tipo="entidade")
        self.assertEqual(r.chave, "Universidade")
        self.assertEqual(r.prefixo, "Un")

    def test_antes_da_primeira_entrada_da_letra(self):
        r = cutter("B")
        self.assertEqual(r.entrada_tabela, "Ba")
        self.assertTrue(r.avisos)

    def test_etiqueta(self):
        r = cutter("Machado de Assis", "Dom Casmurro", classe="869.3", ano="1899", volume="2", exemplar="1")
        self.assertEqual(r.etiqueta, ["869.3", "As848d", "1899", "v.2", "ex.1"])

    def test_numero_no_titulo_gera_erro(self):
        with self.assertRaises(ValueError):
            cutter("Assis", "1984")

    def test_aviso_de_entrada_suspeita(self):
        # "Rung" precede uma lacuna (falta o código 943 na letra R)
        r = cutter("Rungo")
        self.assertEqual(r.entrada_tabela, "Rung")
        self.assertTrue(any("inconsistência" in a for a in r.avisos))


if __name__ == "__main__":
    unittest.main()
