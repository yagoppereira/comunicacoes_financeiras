"""
Conferência de saldo em aberto no DW, para comunicados que mostram valor.

A planilha diz QUEM recebe; o DW diz QUANTO, porque é o estado atual da
carteira. conferir_saldos() aponta quem mudou desde que a planilha foi
montada — pagou um título, pagou tudo, ou venceu título novo — e
usar_saldo_dw() troca o saldo de cada cliente pelo do DW antes do
preparar(). O saldo da planilha fica guardado em `saldo_planilha`, para a
conferência de depois.

FONTE: silver.titulos_cigam, a mesma do aviso de bloqueio: saldo > 0 e
vencimento anterior à data-base. A gold.inadimplencia é reescrita durante o
dia e só tem vencidos; a silver é a carteira do CIGAM título a título.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

SQL_SALDOS = """
SELECT
  t.codigoEmpresa  AS codigo,
  COUNT(*)         AS titulos_dw,
  SUM(t.saldo)     AS saldo_dw
FROM `{project}.silver.titulos_cigam` t
WHERE t.codigoEmpresa IN UNNEST(@codigos)
  AND t.saldo > 0
  AND t.dataVencimento < @data_base
GROUP BY 1
"""

TOLERANCIA = Decimal("0.01")


def _q(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def buscar_saldos_dw(bq, codigos, project: str, data_base: date = None) -> dict:
    """{código: (saldo vencido, nº de títulos)} no DW."""
    from google.cloud import bigquery

    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter("codigos", "STRING", sorted(set(codigos))),
        bigquery.ScalarQueryParameter("data_base", "DATE", data_base or date.today()),
    ])
    df = bq.query(SQL_SALDOS.format(project=project), job_config=config).to_dataframe(
        create_bqstorage_client=False)
    return {r["codigo"]: (_q(r["saldo_dw"]), int(r["titulos_dw"])) for r in df.to_dict("records")}


def comparar(dados: dict, saldos_dw: dict, campo: str = "saldo") -> pd.DataFrame:
    """Uma linha por cliente com saldo da planilha, saldo no DW e situação.
    Pura: recebe o que buscar_saldos_dw() devolveu, para poder ser testada."""
    linhas = []
    for codigo, d in dados.items():
        planilha = _q(d[campo])
        dw, n = saldos_dw.get(codigo, (Decimal("0.00"), 0))
        dif = dw - planilha
        if abs(dif) <= TOLERANCIA:
            situacao = "confere"
        elif dw == 0:
            situacao = "zerado no DW (pagou tudo?)"
        elif dif < 0:
            situacao = "menor no DW (pagou parte?)"
        else:
            situacao = "maior no DW (título novo vencido?)"
        linhas.append({"codigo": codigo, "nome": d.get("nome", ""), "saldo_planilha": planilha,
                       "saldo_dw": dw, "diferenca": dif, "titulos_dw": n, "situacao": situacao})
    df = pd.DataFrame(linhas, columns=["codigo", "nome", "saldo_planilha", "saldo_dw",
                                       "diferenca", "titulos_dw", "situacao"])
    return df.sort_values("diferenca", key=lambda s: s.abs(), ascending=False, ignore_index=True)


def conferir_saldos(bq, dados: dict, project: str, campo: str = "saldo",
                    data_base: date = None) -> pd.DataFrame:
    """Compara o saldo de cada cliente nos `dados` com o vencido em aberto no
    DW hoje. Imprime o resumo e devolve a tabela, diferenças primeiro."""
    df = comparar(dados, buscar_saldos_dw(bq, dados.keys(), project, data_base), campo)
    contagem = df["situacao"].value_counts()
    print(f"Conferência no DW ({len(df)} cliente(s), vencidos até "
          f"{(data_base or date.today()).strftime('%d/%m/%Y')}, exclusive):")
    for situacao, n in contagem.items():
        print(f"   {n:>4}  {situacao}")
    if (df["situacao"] != "confere").any():
        print("Rode dados = titulos.usar_saldo_dw(dados, conf) para o e-mail usar o saldo do DW.")
    return df


def usar_saldo_dw(dados: dict, conferencia: pd.DataFrame, campo: str = "saldo") -> dict:
    """Novo `dados` com o saldo do DW no lugar do da planilha.

    conferencia: o que conferir_saldos() devolveu, NA MESMA sessão — o DW
    muda durante o dia, e é esse retrato que vai congelado na prévia.
    Cliente zerado no DW sai: não há o que oferecer, e o preparar() o lista
    entre os rejeitados ("sem saldo nos dados").
    """
    por_codigo = {r["codigo"]: r for r in conferencia.to_dict("records")}
    faltando = sorted(set(dados) - set(por_codigo))
    if faltando:
        raise ValueError(f"a conferência não tem {len(faltando)} cliente(s) dos dados "
                         f"({', '.join(faltando[:5])}...): rode conferir_saldos() de novo.")
    novo, trocados, zerados = {}, [], []
    for codigo, d in dados.items():
        r = por_codigo[codigo]
        if r["saldo_dw"] <= 0:
            zerados.append(codigo)
            continue
        novo[codigo] = {**d, campo: str(r["saldo_dw"]), f"{campo}_planilha": str(r["saldo_planilha"])}
        if r["situacao"] != "confere":
            trocados.append(codigo)
    total = sum(Decimal(d[campo]) for d in novo.values())
    print(f"Saldo do DW em {len(novo)} cliente(s), total {_brl(total)}; "
          f"{len(trocados)} com valor diferente da planilha"
          + (f" ({', '.join(trocados)})" if trocados else "") + ".")
    if zerados:
        print(f"{len(zerados)} zerado(s) no DW, fora do envio: {', '.join(zerados)}.")
    return novo


def _brl(v) -> str:
    s = f"{Decimal(str(v)):,.2f}"
    return "R$ " + s.replace(",", "@").replace(".", ",").replace("@", ".")
