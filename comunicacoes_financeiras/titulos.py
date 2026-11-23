"""
Conferência de saldo em aberto no DW, para comunicados que mostram valor.

O valor do e-mail vem da PLANILHA aprovada (ex.: aba resumo_ da Black
Friday), não do DW. Esta conferência só aponta quem mudou desde que a
planilha foi montada — pagou um título, pagou tudo, ou entrou título novo
vencido — para a pessoa decidir antes do envio. Ela não troca valor nenhum.

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
        print("O e-mail usa o valor da PLANILHA. Para tirar alguém do envio, remova o "
              "código da lista antes de preparar().")
    return df
