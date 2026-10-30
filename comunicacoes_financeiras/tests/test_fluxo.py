"""Testes da lógica pura: lista, contatos, agrupamento, modelo e fila.

    python -m unittest discover -s comunicacoes_financeiras/tests -t .
"""

import json
import tempfile
import unittest
from pathlib import Path

from comunicacoes_financeiras import contatos, envio, fluxo
from comunicacoes_financeiras.campanha import Campanha, classificar_entrada, separar_entrada
from comunicacoes_financeiras.modelos import _base, unificacao_contratos

MODELO = "unificacao_contratos"
FLAGS = unificacao_contratos.FLAGS_CONTATO


def _contatos(*itens):
    """itens: (email, nfe, boleto)"""
    return json.dumps([
        {"email": e, "recebeEmailNfe": n, "recebeEmailBoleto": b,
         "recebeEmailCartaCobranca": "S", "recebeEmailCobranca": "N"}
        for e, n, b in itens
    ])


def _cad(codigo, doc, divisao="10", contatos_json=None, nome=None):
    return {"codigo": codigo, "nome": nome or f"CLIENTE {codigo}", "fantasia": "",
            "cnpj_cpf": doc, "cnpj_limpo": doc, "divisao": divisao,
            "contatos_json": contatos_json if contatos_json is not None
            else _contatos((f"fin{codigo}@cliente.com.br", "S", "S"))}


class TestEntrada(unittest.TestCase):
    def test_classifica(self):
        self.assertEqual(classificar_entrada("479"), ("codigo", "000479"))
        self.assertEqual(classificar_entrada("08.077.872/0003-21"), ("documento", "08077872000321"))
        self.assertEqual(classificar_entrada("111.111.111-11"), ("documento", "11111111111"))
        self.assertIsNone(classificar_entrada("00.000.000/0000-00")[0])
        self.assertIsNone(classificar_entrada("ABC")[0])
        self.assertIsNone(classificar_entrada("12345678")[0])

    def test_separa_texto_colado(self):
        self.assertEqual(separar_entrada("479\n\n 08.077.872/0003-21 ;1200\t33"),
                         ["479", "08.077.872/0003-21", "1200", "33"])


class TestContatos(unittest.TestCase):
    def test_flags_e_dedupe(self):
        js = _contatos(("A@x.com.br ", "S", "N"), ("a@x.com.br", "N", "N"),
                       ("b@x.com.br", "N", "N"), ("lixo", "S", "S"), ("c@x.com", "N", "S"))
        emails, optout = contatos.emails_elegiveis(js, FLAGS)
        self.assertEqual(emails, ["a@x.com.br", "c@x.com"])
        self.assertEqual(optout, 1)   # b: válido, mas NF-e e boleto = N

    def test_json_ruim_nao_quebra(self):
        self.assertEqual(contatos.emails_elegiveis("", FLAGS), ([], 0))
        self.assertEqual(contatos.emails_elegiveis("{nao json", FLAGS), ([], 0))
        self.assertEqual(contatos.emails_elegiveis(None, FLAGS), ([], 0))

    def test_flag_desconhecida(self):
        with self.assertRaises(ValueError):
            contatos.emails_elegiveis("[]", ["recebeEmailNF"])

    def test_resolver(self):
        cads = [
            _cad("000479", "08077872000321"),
            _cad("000500", "22222222000122", divisao="13"),          # cliente local
            _cad("000679", "33333333000133"),                        # intercompany
            _cad("006381", "11111111111"), _cad("006382", "11111111111"),  # CPF ambíguo
            _cad("000777", "44444444000144",
                 contatos_json=_contatos(("x@y.com", "N", "N"))),    # só opt-out
            _cad("000888", "55555555000155", divisao="20"),          # fornecedor
        ]
        r = contatos.resolver(
            ["479", "08.077.872/0003-21", "500", "679", "111.111.111-11",
             "777", "999", "888", "22.222.222/0001-22"],
            cads, FLAGS)
        self.assertEqual([c["codigo"] for c in r.incluidos], ["000479"])
        motivos = dict(r.rejeitados)
        # o CNPJ do 000479 repete um cadastro já incluído: conta, não rejeita
        self.assertNotIn("08.077.872/0003-21", motivos)
        self.assertEqual(r.repetidos, 1)
        self.assertIn("CLIENTE LOCAL", motivos["500"])
        self.assertIn("LINK2PUMP", motivos["679"])
        self.assertIn("informe o código", motivos["111.111.111-11"])
        self.assertIn("= N", motivos["777"])
        self.assertIn("não existe", motivos["999"])
        self.assertIn("divisão 20", motivos["888"])
        self.assertIn("CLIENTE LOCAL", motivos["22.222.222/0001-22"])

    def test_repetido_rejeitado_aparece_uma_vez(self):
        r = contatos.resolver(["999", "999", 999.0], [], FLAGS)
        self.assertEqual(r.rejeitados, [("999", "código 000999 não existe no CIGAM")])
        self.assertEqual(r.repetidos, 2)

    def test_codigo_lido_como_numero_da_planilha(self):
        # 5115.0 viraria 051150 se o '.0' fosse tratado como dígito
        self.assertEqual(separar_entrada([5115.0, 29, float("nan"), None, "  "]), ["5115", "29"])
        cads = [_cad("005115", "51150000000115")]
        r = contatos.resolver([5115.0], cads, FLAGS)
        self.assertEqual([c["codigo"] for c in r.incluidos], ["005115"])

    def test_documento_com_um_pagante_e_um_local(self):
        cads = [_cad("000100", "66666666000166"),
                _cad("000101", "66666666000166", divisao="13")]
        r = contatos.resolver(["66.666.666/0001-66"], cads, FLAGS)
        self.assertEqual([c["codigo"] for c in r.incluidos], ["000100"])

    def test_chaves_de_busca(self):
        self.assertEqual(contatos.chaves_de_busca("479\n08.077.872/0003-21\nABC"),
                         ({"000479"}, {"08077872000321"}))

    def test_sql_escapa_regex(self):
        sql = contatos.SQL_CADASTROS.format(project="p")
        self.assertIn(r"r'\D'", sql)
        self.assertIn("UNNEST(@codigos)", sql)


class TestAgrupamentoEModelo(unittest.TestCase):
    def setUp(self):
        mesmo = _contatos(("financeiro@grupo.com.br", "S", "S"))
        self.cads = [
            _cad("000001", "10000000000101", contatos_json=mesmo, nome="GRUPO OBRA 1"),
            _cad("000002", "10000000000202", contatos_json=mesmo, nome="GRUPO OBRA 2"),
            _cad("000003", "30000000000103"),
        ]
        self.incluidos = contatos.resolver(["1", "2", "3"], self.cads, FLAGS).incluidos

    def test_agrupa_por_destinatarios(self):
        previa = fluxo.montar_previa(self.incluidos)
        self.assertEqual(list(previa["chave"]), ["000001+000002", "000003"])
        self.assertEqual(list(previa["qtd_cadastros"]), [2, 1])

    def test_email_lista_todos_os_cadastros(self):
        c = Campanha(id_campanha="T", modelo=MODELO)
        fila = fluxo.montar_fila(c, fluxo.montar_previa(self.incluidos))
        job = fila[0]
        self.assertEqual(job.para, ["financeiro@grupo.com.br"])
        for trecho in ("GRUPO OBRA 1", "GRUPO OBRA 2", "10.000.000/0002-02"):
            self.assertIn(trecho, job.html)
            self.assertIn(trecho, job.texto)
        self.assertIn("e mais 1 cadastro", job.assunto)
        self.assertEqual(fila[1].assunto,
                         "Unificação das mensalidades de aluguel e licenciamento – ctasmart – "
                         "CLIENTE 000003 - 30.000.000/0001-03")

    def test_texto_do_financeiro(self):
        job = fluxo.montar_fila(Campanha(id_campanha="T", modelo=MODELO),
                                fluxo.montar_previa(self.incluidos))[1]
        for p in unificacao_contratos.PARAGRAFOS:
            self.assertIn(_base.paragrafos_texto([p]), job.texto)
        self.assertTrue(job.texto.startswith("Prezado cliente,"))
        self.assertIn("<strong", job.html)            # **...** vira negrito
        self.assertNotIn("**", job.html + job.texto)
        self.assertIn("permanecem inalterados", job.html)

    def test_marca(self):
        job = fluxo.montar_fila(Campanha(id_campanha="T", modelo=MODELO),
                                fluxo.montar_previa(self.incluidos))[0]
        self.assertIn(f"cid:{_base.CID_CABECALHO}", job.html)
        for cor in (_base.NIGHT, _base.COBALT, _base.VERDE):
            self.assertIn(cor, job.html)
        # brandbook: o nome é sempre minúsculo
        for errado in ("Cta Smart", "CTA Smart", "CtaSmart", "Ctasmart"):
            self.assertNotIn(errado, job.html + job.texto + job.assunto)
        for caminho in _base.IMAGENS.values():
            self.assertTrue(Path(caminho).is_file(), caminho)
        self.assertNotIn("cid:", fluxo.html_para_visualizar(job.html))

    def test_aviso_de_teste_dentro_do_body(self):
        job = fluxo.montar_fila(Campanha(id_campanha="T", modelo=MODELO),
                                fluxo.montar_previa(self.incluidos))[0]
        h = envio.aplicar_redirecionamento(job, "eu@ctasmart.com.br").html
        self.assertTrue(h.startswith("<!doctype html>"))
        self.assertLess(h.index("<body"), h.index("MODO TESTE"))

    def test_nome_com_html_escapado(self):
        cads = [_cad("000009", "90000000000109", nome="A & B <LTDA>")]
        inc = contatos.resolver(["9"], cads, FLAGS).incluidos
        job = fluxo.montar_fila(Campanha(id_campanha="T", modelo=MODELO),
                                fluxo.montar_previa(inc))[0]
        self.assertIn("A &amp; B &lt;LTDA&gt;", job.html)

    def test_copia_padrao_sem_repetir_destinatario(self):
        c = Campanha(id_campanha="T", modelo=MODELO,
                     copia_padrao=("contato.financeiro@ctasmart.com.br", "financeiro@grupo.com.br"))
        job = fluxo.montar_fila(c, fluxo.montar_previa(self.incluidos))[0]
        self.assertEqual(job.cc, ["contato.financeiro@ctasmart.com.br"])

    def test_parametro_desconhecido(self):
        c = Campanha(id_campanha="T", modelo=MODELO, parametros={"data_limite": "x"})
        with self.assertRaises(ValueError):
            fluxo.montar_fila(c, fluxo.montar_previa(self.incluidos))

    def test_lista_da_planilha(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lista.xlsx"
            with pd.ExcelWriter(p) as w:
                pd.DataFrame({"Contrato": [1]}).to_excel(w, sheet_name="UNIFICAÇÃO ", index=False)
                pd.DataFrame({"COD CIGAM": [5115, None, 29.0, 5115]}).to_excel(
                    w, sheet_name="lista comunicado", index=False)
            valores = fluxo.ler_lista_planilha(p)
            self.assertEqual(separar_entrada(valores), ["5115", "29", "5115"])
            with self.assertRaises(ValueError):
                fluxo.ler_lista_planilha(p, aba="não existe")
            with self.assertRaises(ValueError):
                fluxo.ler_lista_planilha(p, coluna="CNPJ")
            self.assertEqual(fluxo.ler_lista_planilha(p, aba=" UNIFICAÇÃO", coluna="contrato"), [1])

    def test_id_do_drive(self):
        fid = "111fwG0ouHLTcxOFmzR2IhH0ADLcLy6Xf"
        self.assertEqual(fluxo.id_do_drive(
            f"https://docs.google.com/spreadsheets/d/{fid}/edit?gid=285068875#gid=285068875"), fid)
        self.assertEqual(fluxo.id_do_drive(f"https://drive.google.com/file/d/{fid}/view"), fid)
        self.assertEqual(fluxo.id_do_drive(fid), fid)
        with self.assertRaises(ValueError):
            fluxo.id_do_drive("planilha.xlsx")

    def test_cadastro_novo_no_grupo_de_um_ja_avisado(self):
        # O caso real: 002148 recebeu sozinho; depois a planilha ganhou o 002147,
        # com os mesmos destinatários, e os dois viraram um e-mail só. Antes o
        # e-mail inteiro era pulado e o 002147 ficava sem aviso.
        mesmo = _contatos(("fin@empresa.com.br", "S", "S"))
        a = _cad("002148", "21480000000101", contatos_json=mesmo, nome="EMPRESA MATRIZ")
        b = _cad("002147", "21470000000101", contatos_json=mesmo, nome="EMPRESA FILIAL")
        reg, c = RegistroMemoria(), Campanha.producao("T", MODELO)

        antes = fluxo.montar_previa(contatos.resolver(["2148"], [a], FLAGS).incluidos)
        fluxo.disparar(c, antes, lambda j: None, reg, pausa_segundos=0)

        depois = fluxo.montar_previa(contatos.resolver(["2148", "2147"], [a, b], FLAGS).incluidos)
        self.assertEqual(list(depois["chave"]), ["002148+002147"])
        enviados = []
        r = fluxo.disparar(c, depois, enviados.append, reg, pausa_segundos=0)
        self.assertEqual([j.codigos for j in enviados], [("002147",)])
        self.assertEqual(enviados[0].para, ["fin@empresa.com.br"])
        self.assertIn("EMPRESA FILIAL", enviados[0].html)
        self.assertNotIn("EMPRESA MATRIZ", enviados[0].html)   # já foi avisado
        self.assertEqual(r.pulados, [])

        # terceira execução: tudo avisado, o grupo inteiro é pulado
        enviados = []
        r = fluxo.disparar(c, depois, enviados.append, reg, pausa_segundos=0)
        self.assertEqual(enviados, [])
        self.assertEqual(r.pulados, [("002148+002147", "já enviado nesta campanha")])

    def test_previa_csv_preserva_zero(self):
        previa = fluxo.montar_previa(self.incluidos)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "previa.csv"
            fluxo.salvar_previa(previa, p)
            lida = fluxo.ler_previa(p)
        self.assertEqual(list(lida["chave"]), ["000001+000002", "000003"])
        c = Campanha(id_campanha="T", modelo=MODELO)
        self.assertEqual(fluxo.montar_fila(c, lida)[0].codigos, ("000001", "000002"))

    def test_documento(self):
        self.assertEqual(_base.formatar_documento("7636657001241"), "07.636.657/0012-41")
        self.assertEqual(_base.formatar_documento("12345678901"), "123.456.789-01")
        self.assertEqual(_base.formatar_documento(None), "")


class RegistroMemoria:
    def __init__(self):
        self.linhas = []

    def ja_enviados(self, id_campanha, modo, enviado_para=None):
        return envio._codigos_enviados(self.linhas, id_campanha, modo, enviado_para)

    def gravar(self, linha):
        self.linhas.append(linha)


def _job(*codigos, para=("a@x.com",)):
    return envio.Job(codigos=codigos, nome="X", para=list(para), cc=[],
                     assunto="A", html="<p>h</p>", texto="t")


class TestDisparo(unittest.TestCase):
    def test_producao_sem_confirmacao_recusa(self):
        c = Campanha(id_campanha="T", modelo=MODELO, dry_run=False)
        with self.assertRaises(RuntimeError):
            envio.disparar([_job("000001")], c, lambda j: None, RegistroMemoria())

    def test_ensaio_nao_envia_nem_loga(self):
        enviados, reg = [], RegistroMemoria()
        c = Campanha.ensaio("T", MODELO)
        r = envio.disparar([_job("000001"), _job("000002", para=())], c,
                           enviados.append, reg, pausa_segundos=0)
        self.assertEqual(enviados, [])
        self.assertEqual(reg.linhas, [])
        self.assertEqual(r.enviados, ["000001"])
        self.assertEqual(r.pulados, [("000002", "sem destinatário")])

    def test_teste_redireciona_e_mostra_reais(self):
        enviados, reg = [], RegistroMemoria()
        c = Campanha.teste("T", MODELO, para="eu@ctasmart.com.br")
        envio.disparar([_job("000001", para=("a@x.com", "b@x.com"))], c,
                       enviados.append, reg, pausa_segundos=0)
        self.assertEqual(enviados[0].para, ["eu@ctasmart.com.br"])
        self.assertTrue(enviados[0].assunto.startswith("[TESTE 000001]"))
        self.assertIn("a@x.com, b@x.com", enviados[0].html)
        self.assertEqual(reg.linhas[0]["para_real"], "a@x.com; b@x.com")
        self.assertEqual(reg.linhas[0]["modo"], "TESTE")

    def test_idempotencia_por_codigo_mesmo_com_reagrupamento(self):
        reg = RegistroMemoria()
        c = Campanha.producao("T", MODELO)
        envio.disparar([_job("000001", "000002")], c, lambda j: None, reg, pausa_segundos=0)
        enviados = []
        r = envio.disparar([_job("000002"), _job("000003")], c, enviados.append, reg,
                           pausa_segundos=0)
        self.assertEqual([j.chave for j in enviados], ["000003"])
        self.assertEqual(r.pulados, [("000002", "já enviado nesta campanha")])

    def test_log_de_teste_nao_conta_para_producao(self):
        reg = RegistroMemoria()
        envio.disparar([_job("000001")], Campanha.teste("T", MODELO, para="eu@ctasmart.com.br"),
                       lambda j: None, reg, pausa_segundos=0)
        enviados = []
        envio.disparar([_job("000001")], Campanha.producao("T", MODELO),
                       enviados.append, reg, pausa_segundos=0)
        self.assertEqual(len(enviados), 1)

    def test_reenviar_so_vale_para_teste(self):
        reg = RegistroMemoria()
        t = Campanha.teste("T", MODELO, para="eu@ctasmart.com.br")
        envio.disparar([_job("000001")], t, lambda j: None, reg, pausa_segundos=0)
        enviados = []
        envio.disparar([_job("000001")], Campanha.teste("T", MODELO, para="eu@ctasmart.com.br",
                                                        reenviar=True),
                       enviados.append, reg, pausa_segundos=0)
        self.assertEqual(len(enviados), 1)

    def test_teste_para_outro_endereco_envia_de_novo(self):
        # O caso real: teste para uma pessoa, depois para outra, mesma campanha.
        reg = RegistroMemoria()
        fila = [_job("005115"), _job("005177", "005180")]
        envio.disparar(fila, Campanha.teste("T", MODELO, para="yago@ctasmart.com.br"),
                       lambda j: None, reg, pausa_segundos=0)

        enviados = []
        r = envio.disparar(fila, Campanha.teste("T", MODELO, para="Paul@ctasmart.com.br"),
                           enviados.append, reg, pausa_segundos=0)
        self.assertEqual([j.chave for j in enviados], ["005115", "005177+005180"])
        self.assertEqual(r.pulados, [])

        # repetir para o mesmo endereço (maiúscula não importa) continua pulando
        enviados = []
        r = envio.disparar(fila, Campanha.teste("T", MODELO, para="paul@ctasmart.com.br"),
                           enviados.append, reg, pausa_segundos=0)
        self.assertEqual(enviados, [])
        self.assertIn("paul@ctasmart.com.br", r.pulados[0][1])
        self.assertIn("reenviar=True", r.pulados[0][1])

        # e nada disso conta para produção
        self.assertEqual(reg.ja_enviados("T", "PRODUCAO"), set())

    def test_teto_diario_deixa_pendente(self):
        c = Campanha.producao("T", MODELO, teto_diario=3)
        enviados = []
        r = envio.disparar([_job("000001", para=("a@x.com", "b@x.com")),
                            _job("000002", para=("c@x.com", "d@x.com"))],
                           c, enviados.append, RegistroMemoria(), pausa_segundos=0)
        self.assertEqual(len(enviados), 1)
        self.assertEqual(r.pendentes, ["000002"])

    def test_falha_loga_e_segue(self):
        reg = RegistroMemoria()

        def enviar(job):
            if "000001" in job.codigos:
                raise OSError("smtp caiu")

        r = envio.disparar([_job("000001"), _job("000002")], Campanha.producao("T", MODELO),
                           enviar, reg, pausa_segundos=0)
        self.assertEqual(r.enviados, ["000002"])
        self.assertEqual([l["status"] for l in reg.linhas], ["FALHA", "ENVIADO"])
        # a falha não conta como enviado: a próxima execução tenta de novo
        self.assertEqual(reg.ja_enviados("T", "PRODUCAO"), {"000002"})

    def test_registro_csv(self):
        with tempfile.TemporaryDirectory() as d:
            reg = envio.RegistroCSV(Path(d) / "sub" / "log.csv")
            self.assertEqual(reg.ja_enviados("T", "PRODUCAO"), set())
            envio.disparar([_job("000001", "000002")], Campanha.producao("T", MODELO),
                           lambda j: None, reg, pausa_segundos=0)
            self.assertEqual(reg.ja_enviados("T", "PRODUCAO"), {"000001", "000002"})
            self.assertEqual(reg.ja_enviados("OUTRA", "PRODUCAO"), set())

    def test_campanha_valida(self):
        with self.assertRaises(ValueError):
            Campanha(id_campanha="T", modelo=MODELO, redirecionar_para="nao-e-email")
        with self.assertRaises(ValueError):
            Campanha(id_campanha="T", modelo=MODELO, redirecionar_para="a@b.com",
                     confirmo_producao=True)
        with self.assertRaises(ValueError):
            Campanha(id_campanha=" ", modelo=MODELO)


if __name__ == "__main__":
    unittest.main()
