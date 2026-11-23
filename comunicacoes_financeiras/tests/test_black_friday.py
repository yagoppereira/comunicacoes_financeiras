"""Testes da campanha Black Friday: planilha, conta, e-mail e conferência."""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import pandas as pd

from comunicacoes_financeiras import contatos, fluxo, titulos
from comunicacoes_financeiras.campanha import Campanha
from comunicacoes_financeiras.modelos import black_friday as bf

MODELO = "black_friday"


def _cad(codigo, doc, emails=("fin@cliente.com.br",), nome=None):
    return {"codigo": codigo, "nome": nome or f"CLIENTE {codigo}", "fantasia": "",
            "cnpj_cpf": doc, "cnpj_limpo": doc, "divisao": "10",
            "contatos_json": json.dumps([{"email": e, "recebeEmailNfe": "S"} for e in emails])}


def _previa(lista, cads, dados):
    r = contatos.resolver(lista, cads, bf.FLAGS_CONTATO)
    fluxo._anexar_dados(r, dados, bf.DADOS_OBRIGATORIOS)
    return fluxo.montar_previa(r.incluidos), r


class TestPlanilha(unittest.TestCase):
    def test_codigo_do_rotulo(self):
        self.assertEqual(bf.codigo_do_rotulo("003262 - PEDRO HENRIQUE MOURA E CIA LTDA"), "003262")
        # dígito no nome não pode entrar no código
        self.assertEqual(bf.codigo_do_rotulo("003960 - A12 COMERCIO DE CEREAIS LTDA"), "003960")
        self.assertEqual(bf.codigo_do_rotulo(479.0), "000479")
        with self.assertRaises(ValueError):
            bf.codigo_do_rotulo("TRANSPORTADORA SEM CODIGO")

    def test_valor_monetario(self):
        self.assertEqual(bf.valor_monetario(22117.6), Decimal("22117.60"))
        self.assertEqual(bf.valor_monetario("R$ 22.117,60"), Decimal("22117.60"))
        self.assertEqual(bf.valor_monetario("R$ 13,50"), Decimal("13.50"))
        self.assertEqual(bf.valor_monetario(8000), Decimal("8000.00"))
        with self.assertRaises(ValueError):
            bf.valor_monetario("abc")

    def test_selecionar_so_sim(self):
        linhas = [
            {"empresa": "003262 - PEDRO HENRIQUE MOURA", "considerar": "Sim", "saldo": 22117.6},
            {"empresa": "002378 - TRANSPORTADORA PRINT", "considerar": "Não", "saldo": 22715.73},
            {"empresa": "004087 - VALEBETON", "considerar": " sim ", "saldo": "R$ 8.000,00"},
            {"empresa": None, "considerar": None, "saldo": None},
        ]
        lista, dados = bf.selecionar(linhas)
        self.assertEqual(lista, ["003262", "004087"])
        self.assertEqual(dados["004087"], {"saldo": "8000.00", "nome": "VALEBETON"})

    def test_selecionar_recusa_planilha_com_problema(self):
        with self.assertRaises(ValueError) as e:
            bf.selecionar([
                {"empresa": "000001 - A", "considerar": "Sim", "saldo": 100},
                {"empresa": "000001 - A", "considerar": "Sim", "saldo": 200},
                {"empresa": "SEM CODIGO", "considerar": "Sim", "saldo": 10},
                {"empresa": "000003 - C", "considerar": "Sim", "saldo": 0},
            ])
        msg = str(e.exception)
        self.assertIn("duas vezes", msg)
        self.assertIn("código CIGAM", msg)
        self.assertIn("nada a oferecer", msg)

    def test_aba_com_anotacao_acima_do_cabecalho(self):
        # como a resumo_: linha 1 com anotação, cabeçalho na 2, "Motivo" repetido
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bf.xlsx"
            pd.DataFrame([
                ["", "considerar o que for sim", "", "", "", "30%"],
                ["Empresa", "Considerar?", "Motivo", "Total Saldo", "Motivo", "2022"],
                ["003262 - PEDRO", "Sim", "Inadimplência Crônica", 22117.6, "Outro", 0],
                [None, None, None, None, None, None],
                ["002378 - PRINT", "Não", "Negociação", 22715.73, None, None],
            ]).to_excel(p, sheet_name="resumo_", index=False, header=False)
            linhas = fluxo.ler_tabela_planilha(p, "resumo_", bf.COLUNAS_PLANILHA)
            self.assertEqual(len(linhas), 2)
            self.assertEqual(linhas[0], {"empresa": "003262 - PEDRO", "considerar": "Sim", "saldo": 22117.6})
            with self.assertRaises(ValueError):
                fluxo.ler_tabela_planilha(p, "resumo_", {"x": "Coluna que não existe"})


class TestConta(unittest.TestCase):
    def test_calcular(self):
        self.assertEqual(bf.calcular("22117.60", 20),
                         (Decimal("22117.60"), Decimal("4423.52"), Decimal("17694.08")))
        # meio-pra-cima no centavo: 20% de 0,03 = 0,006 -> 0,01
        self.assertEqual(bf.calcular("0.03", 20)[1], Decimal("0.01"))

    def test_total_e_soma_dos_cadastros(self):
        clientes = [{"dados": {"saldo": "0.03"}}, {"dados": {"saldo": "0.03"}}]
        # por cadastro: 0,01 + 0,01 = 0,02 (no total direto daria 0,01)
        self.assertEqual(bf.totais(clientes, 20)[1], Decimal("0.02"))


class TestEmail(unittest.TestCase):
    def setUp(self):
        self.c = Campanha(id_campanha="BF", modelo=MODELO)

    def test_um_cadastro(self):
        previa, _ = _previa(["3262"], [_cad("003262", "11111111000111", nome="PEDRO LTDA")],
                            {"003262": {"saldo": "22117.60"}})
        job = fluxo.montar_fila(self.c, previa)[0]
        for t in ("R$ 22.117,60", "R$ 4.423,52", "R$ 17.694,08", "28/11/2026", "(51) 99888-0734"):
            self.assertIn(t, job.html)
            self.assertIn(t, job.texto)
        self.assertIn("20% DE DESCONTO", job.texto)
        self.assertIn("Enviaremos a conta bancária ou a chave PIX com o desconto já aplicado.", job.texto)
        self.assertNotIn("boleto", job.texto + job.html)
        self.assertEqual(job.assunto, "Oferta Black Friday: 20% OFF - Títulos em Atraso – ctasmart – "
                                      "PEDRO LTDA - 11.111.111/0001-11")
        self.assertNotIn("Saldo em aberto por cadastro", job.texto)

    def test_varios_cadastros_mesmo_destinatario(self):
        cads = [_cad("004087", "22222222000101", nome="VALEBETON"),
                _cad("004092", "22222222000202", nome="VALEBETON")]
        previa, _ = _previa(["4087", "4092"], cads,
                            {"004087": {"saldo": "8000.00"}, "004092": {"saldo": "8000.00"}})
        self.assertEqual(list(previa["chave"]), ["004087+004092"])
        job = fluxo.montar_fila(self.c, previa)[0]
        self.assertIn("Saldo em aberto por cadastro", job.texto)
        self.assertIn("22.222.222/0002-02: R$ 8.000,00", job.texto)
        self.assertIn("R$ 16.000,00", job.html)          # total
        self.assertIn("R$ 12.800,00", job.html)          # à vista
        resumo = bf.resumo_previa(previa, self.c)
        self.assertEqual(resumo.loc[0, "valor_final"], Decimal("12800.00"))

    def test_percentual_e_prazo_por_parametro(self):
        c = Campanha(id_campanha="BF", modelo=MODELO,
                     parametros={"percentual": "25", "prazo": "05/12/2026"})
        previa, _ = _previa(["1"], [_cad("000001", "33333333000133")], {"000001": {"saldo": "1000"}})
        job = fluxo.montar_fila(c, previa)[0]
        self.assertIn("25% OFF", job.assunto)
        self.assertIn("R$ 750,00", job.texto)
        self.assertIn("05/12/2026", job.texto)
        self.assertNotIn("28/11/2026", job.texto + job.html)

    def test_sem_saldo_sai_dos_incluidos(self):
        previa, r = _previa(["1", "2"], [_cad("000001", "33333333000133"), _cad("000002", "44444444000144")],
                            {"000001": {"saldo": "1000"}})
        self.assertEqual(list(previa["chave"]), ["000001"])
        self.assertIn("sem saldo nos dados", dict(r.rejeitados)["000002"])

    def test_preparar_exige_dados(self):
        with self.assertRaises(ValueError):
            fluxo.preparar(None, self.c, ["1"])


class TestConferencia(unittest.TestCase):
    def test_comparar(self):
        dados = {"000001": {"saldo": "100.00", "nome": "A"}, "000002": {"saldo": "100.00", "nome": "B"},
                 "000003": {"saldo": "100.00", "nome": "C"}, "000004": {"saldo": "100.00", "nome": "D"}}
        dw = {"000001": (Decimal("100.00"), 2), "000002": (Decimal("40.00"), 1),
              "000004": (Decimal("150.00"), 3)}
        df = titulos.comparar(dados, dw).set_index("codigo")
        self.assertEqual(df.loc["000001", "situacao"], "confere")
        self.assertTrue(df.loc["000002", "situacao"].startswith("menor"))
        self.assertTrue(df.loc["000003", "situacao"].startswith("zerado"))
        self.assertTrue(df.loc["000004", "situacao"].startswith("maior"))
        self.assertEqual(df.loc["000002", "diferenca"], Decimal("-60.00"))

    def test_usar_saldo_dw(self):
        # o caso real: Transjofer pagou a adesão, Ourotrans venceu título novo
        dados = {"004958": {"saldo": "5816.66", "nome": "TRANSJOFER"},
                 "002889": {"saldo": "13973.91", "nome": "OUROTRANS"},
                 "003262": {"saldo": "22117.60", "nome": "PEDRO"},
                 "000001": {"saldo": "100.00", "nome": "PAGOU TUDO"}}
        dw = {"004958": (Decimal("3566.66"), 2), "002889": (Decimal("15146.67"), 36),
              "003262": (Decimal("22117.60"), 23)}
        novo = titulos.usar_saldo_dw(dados, titulos.comparar(dados, dw))
        self.assertEqual(novo["004958"]["saldo"], "3566.66")
        self.assertEqual(novo["004958"]["saldo_planilha"], "5816.66")
        self.assertEqual(novo["002889"]["saldo"], "15146.67")
        self.assertEqual(novo["003262"]["saldo"], "22117.60")
        self.assertEqual(novo["003262"]["nome"], "PEDRO")
        self.assertNotIn("000001", novo)                    # zerado no DW: sai
        self.assertEqual(dados["004958"]["saldo"], "5816.66")  # o original não muda

        # e o e-mail sai com o valor do DW
        previa, r = _previa(["4958", "1"], [_cad("004958", "55555555000155"), _cad("000001", "66666666000166")], novo)
        job = fluxo.montar_fila(Campanha(id_campanha="BF", modelo=MODELO), previa)[0]
        self.assertIn("R$ 3.566,66", job.texto)
        self.assertNotIn("5.816,66", job.texto + job.html)
        self.assertIn("000001", dict(r.rejeitados))

    def test_usar_saldo_dw_com_conferencia_de_outros_dados(self):
        with self.assertRaises(ValueError):
            titulos.usar_saldo_dw({"000009": {"saldo": "1"}}, titulos.comparar({}, {}))


if __name__ == "__main__":
    unittest.main()
