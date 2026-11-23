"""
Oferta Black Friday: desconto na quitação dos títulos em atraso.

O texto é o da aba "Modelo" da planilha "Black Friday (Inadimplência)". O
percentual e o prazo entram como parâmetro da campanha (padrão: 20% e
28/11/2026, como no Modelo), para o mesmo texto servir a outra rodada.

O VALOR vem da planilha, não do DW: aba resumo_, coluna "Total Saldo",
só as linhas com "Considerar?" = Sim (ver selecionar()). O e-mail mostra
saldo, desconto e o valor à vista; o desconto é calculado por cadastro, em
Decimal e meio-pra-cima, e o total é a soma dos cadastros — assim a conta do
quadro fecha linha a linha com o que o financeiro vai emitir.

Um e-mail pode cobrir vários cadastros (mesmos destinatários): nesse caso
entra o quadro com o saldo de cada um, e o resumo mostra o total.
"""

import html
import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from . import _base

NOME = "Oferta Black Friday — desconto nos títulos em atraso"
FLAGS_CONTATO = ("recebeEmailNfe", "recebeEmailBoleto")
PARAMETROS = {"percentual": False, "prazo": False}
DADOS_OBRIGATORIOS = ("saldo",)

PERCENTUAL_PADRAO = "20"
PRAZO_PADRAO = "28/11/2026"
WHATSAPP = "(51) 99888-0734"

ASSUNTO = "Oferta Black Friday: {pct}% OFF - Títulos em Atraso – ctasmart – {identificacao}"
ROTULO = "Black Friday"
TITULO = "Oferta Black Friday: {pct}% OFF - Títulos em Atraso"
PREHEADER = "{pct}% de desconto na quitação de todos os títulos em atraso, à vista até {prazo}."

SAUDACAO = "Prezado cliente,"
ABERTURA = ("Nesta Black Friday, preparamos uma condição exclusiva para você regularizar "
            "suas pendências com a gente:")
DESTAQUE = "{pct}% DE DESCONTO na quitação de todos os títulos em atraso."
COMO_APROVEITAR = "Como aproveitar:"
PASSOS = [
    "Responda este e-mail ou chame a gente no whatsapp {whatsapp}.",
    "Enviaremos o boleto ou a chave PIX com o desconto já aplicado.",
    "Faça o pagamento até {prazo}.",
]
FECHAMENTO = [
    "A condição é válida apenas para a quitação de todos os títulos em atraso, com "
    "pagamento à vista até {prazo}, e não será prorrogada.",
    "Aproveite esta oportunidade para colocar sua conta em dia e evitar a negativação "
    "do seu nome.",
    "Ficamos à disposição para qualquer dúvida.",
]

ROTULO_SALDO = "Seu saldo em aberto hoje"
ROTULO_DESCONTO = "Desconto Black Friday ({pct}%)"
ROTULO_FINAL = "À vista até {prazo}"


# ---------------------------------------------------------------------------
# Leitura da planilha
# ---------------------------------------------------------------------------

COLUNAS_PLANILHA = {"empresa": "Empresa", "considerar": "Considerar?", "saldo": "Total Saldo"}


def valor_monetario(v) -> Decimal:
    """22117.6 (número da planilha) ou 'R$ 22.117,60' (texto) -> Decimal('22117.60')."""
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v != v:
            raise ValueError("valor vazio")
        return Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    s = re.sub(r"[R$\s]", "", str(v or ""))
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"valor {v!r} não é um número") from None


def codigo_do_rotulo(v) -> str:
    """'003262 - PEDRO HENRIQUE MOURA E CIA LTDA' -> '003262'. Só o número do
    começo: nome com dígito ('A12 COMERCIO') não pode entrar no código."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    m = re.match(r"\s*(\d{1,6})(?!\d)", str(v or ""))
    if not m:
        raise ValueError(f"não achei o código CIGAM no começo de {v!r}")
    return m.group(1).zfill(6)


def selecionar(linhas: list) -> tuple:
    """(lista de códigos, dados por código) das linhas com Considerar? = Sim.

    linhas: o que fluxo.ler_tabela_planilha(..., colunas=COLUNAS_PLANILHA)
    devolve. Código repetido com saldo diferente é erro: não dá para saber
    qual valor oferecer.
    """
    lista, dados, problemas = [], {}, []
    for i, l in enumerate(linhas, start=1):
        if str(l.get("considerar") or "").strip().casefold() != "sim":
            continue
        try:
            codigo = codigo_do_rotulo(l.get("empresa"))
            saldo = valor_monetario(l.get("saldo"))
        except ValueError as e:
            problemas.append(f"linha {i}: {e}")
            continue
        if saldo <= 0:
            problemas.append(f"linha {i} ({codigo}): saldo {saldo} — nada a oferecer")
            continue
        if codigo in dados:
            if Decimal(dados[codigo]["saldo"]) != saldo:
                problemas.append(f"{codigo} aparece duas vezes com saldos diferentes")
            continue
        nome = str(l.get("empresa")).split("-", 1)[-1].strip()
        lista.append(codigo)
        dados[codigo] = {"saldo": str(saldo), "nome": nome}
    if problemas:
        raise ValueError("planilha com problema — corrija antes de preparar:\n   "
                         + "\n   ".join(problemas))
    total = sum(Decimal(d["saldo"]) for d in dados.values())
    print(f"{len(lista)} cliente(s) com Considerar? = Sim, saldo total {_base_brl(total)}.")
    return lista, dados


# ---------------------------------------------------------------------------
# Conta
# ---------------------------------------------------------------------------

def _pct(campanha) -> Decimal:
    return Decimal(str(campanha.parametros.get("percentual") or PERCENTUAL_PADRAO))


def _prazo(campanha) -> str:
    return str(campanha.parametros.get("prazo") or PRAZO_PADRAO)


def calcular(saldo, pct) -> tuple:
    """(saldo, desconto, valor final) de UM cadastro."""
    saldo = Decimal(str(saldo))
    desconto = (saldo * Decimal(str(pct)) / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return saldo, desconto, saldo - desconto


def totais(clientes: list, pct) -> tuple:
    contas = [calcular(c["dados"]["saldo"], pct) for c in clientes]
    return tuple(sum(c[i] for c in contas) for i in range(3))


def _base_brl(v) -> str:
    s = f"{Decimal(str(v)):,.2f}"
    return "R$ " + s.replace(",", "@").replace(".", ",").replace("@", ".")


def _pct_texto(pct: Decimal) -> str:
    return f"{pct.normalize():f}".replace(".", ",")


# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------

def _quadro_valores_html(saldo, desconto, final, pct_txt, prazo) -> str:
    """Saldo, desconto e valor final empilhados: cabe no celular sem virar
    três colunas espremidas. A última linha é o número que importa."""
    cel = f"padding:12px 18px;font-family:{_base.FONTE_TEXTO};font-size:14px"
    val = f"padding:12px 18px;text-align:right;white-space:nowrap;font-family:{_base.FONTE_TITULO}"
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;margin:6px 0 24px;border:1px solid {_base.BORDA}">'
        f'<tr><td style="{cel};color:{_base.SLATE_700}">{html.escape(ROTULO_SALDO)}</td>'
        f'<td style="{val};font-size:15px;color:{_base.NIGHT}">{_base_brl(saldo)}</td></tr>'
        f'<tr><td style="{cel};color:{_base.SLATE_700};border-top:1px solid {_base.BORDA}">'
        f'{html.escape(ROTULO_DESCONTO.format(pct=pct_txt))}</td>'
        f'<td style="{val};font-size:15px;color:{_base.VERDE_DARK};border-top:1px solid {_base.BORDA}">'
        f'− {_base_brl(desconto)}</td></tr>'
        f'<tr><td style="{cel};background:{_base.NIGHT};color:#FFFFFF;font-weight:500">'
        f'{html.escape(ROTULO_FINAL.format(prazo=prazo))}</td>'
        f'<td style="{val};background:{_base.NIGHT};color:{_base.VERDE};font-size:22px;font-weight:700">'
        f'{_base_brl(final)}</td></tr></table>')


def _quadro_cadastros_html(clientes, pct) -> str:
    """Com vários cadastros no mesmo e-mail: o saldo de cada um, antes do total."""
    linhas = []
    for i, c in enumerate(clientes):
        borda = f"border-top:1px solid {_base.BORDA};" if i else ""
        saldo, _, final = calcular(c["dados"]["saldo"], pct)
        linhas.append(
            f'<tr><td style="{borda}padding:9px 0;font-family:{_base.FONTE_TEXTO};font-size:14px;'
            f'color:{_base.NIGHT}">{html.escape(_base.razao_social(c))}'
            f'<div style="font-size:12px;color:{_base.SLATE_700}">'
            f'{_base.formatar_documento(c.get("cnpj_cpf")) or "—"}</div></td>'
            f'<td align="right" style="{borda}padding:9px 0 9px 14px;font-family:{_base.FONTE_TEXTO};'
            f'font-size:14px;color:{_base.NIGHT};white-space:nowrap">{_base_brl(saldo)}</td></tr>')
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;margin:4px 0 12px">'
        f'<tr><td style="background:{_base.COBALT_5};border-left:4px solid {_base.COBALT};padding:14px 18px">'
        f'<div style="font-family:{_base.FONTE_TITULO};font-size:10px;font-weight:600;letter-spacing:2px;'
        f'color:{_base.COBALT_DARK};text-transform:uppercase;margin-bottom:4px">'
        f'Saldo em aberto por cadastro</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse">{"".join(linhas)}</table></td></tr></table>')


def _destaque_html(texto) -> str:
    return (f'<p style="margin:6px 0 18px;padding:14px 18px;background:{_base.COBALT_5};'
            f'border-left:4px solid {_base.VERDE};font-family:{_base.FONTE_TITULO};font-size:16px;'
            f'font-weight:700;color:{_base.COBALT_DARK}">{html.escape(texto)}</p>')


def _sem_quebra_no_telefone(texto_html: str) -> str:
    """O hífen do telefone é ponto de quebra para o navegador: no celular o
    número saía partido em duas linhas."""
    tel = html.escape(WHATSAPP)
    return texto_html.replace(tel, f'<span style="white-space:nowrap">{tel}</span>')


def _passos_html(passos) -> str:
    linhas = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;vertical-align:top">'
        f'<div style="width:22px;height:22px;line-height:22px;text-align:center;border-radius:11px;'
        f'background:{_base.COBALT};color:#FFFFFF;font-family:{_base.FONTE_TITULO};font-size:12px;'
        f'font-weight:600">{n}</div></td>'
        f'<td style="padding:4px 0;font-family:{_base.FONTE_TEXTO};font-size:15px;line-height:1.5;'
        f'color:{_base.NIGHT_LIGHT}">{_sem_quebra_no_telefone(html.escape(p))}</td></tr>'
        for n, p in enumerate(passos, start=1))
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse;margin:0 0 20px">{linhas}</table>')


def montar(clientes: list, campanha) -> dict:
    if not clientes:
        raise ValueError("nenhum cadastro para montar o e-mail.")
    for c in clientes:
        if Decimal(str((c.get("dados") or {}).get("saldo") or 0)) <= 0:
            raise ValueError(f"{c.get('codigo')}: sem saldo — não se oferece desconto sobre nada.")

    pct, prazo = _pct(campanha), _prazo(campanha)
    pct_txt = _pct_texto(pct)
    saldo, desconto, final = totais(clientes, pct)
    destaque = DESTAQUE.format(pct=pct_txt)
    passos = [p.format(whatsapp=WHATSAPP, prazo=prazo) for p in PASSOS]
    fechamento = [p.format(prazo=prazo) for p in FECHAMENTO]
    varios = len(clientes) > 1

    corpo_html = "\n".join([
        _base.paragrafos_html([SAUDACAO, ABERTURA]),
        _destaque_html(destaque),
        _quadro_cadastros_html(clientes, pct) if varios else "",
        _quadro_valores_html(saldo, desconto, final, pct_txt, prazo),
        f'<p style="margin:0 0 8px;font-family:{_base.FONTE_TITULO};font-weight:600;'
        f'color:{_base.NIGHT}">{html.escape(COMO_APROVEITAR)}</p>',
        _passos_html(passos),
        _base.paragrafos_html(fechamento),
    ])

    blocos = [SAUDACAO, ABERTURA, destaque]
    if varios:
        blocos.append("Saldo em aberto por cadastro:\n" + "\n".join(
            f"  - {_base.razao_social(c)} - {_base.formatar_documento(c.get('cnpj_cpf')) or 's/ documento'}: "
            f"{_base_brl(calcular(c['dados']['saldo'], pct)[0])}" for c in clientes))
    blocos.append(f"{ROTULO_SALDO}: {_base_brl(saldo)}\n"
                  f"{ROTULO_DESCONTO.format(pct=pct_txt)}: - {_base_brl(desconto)}\n"
                  f"{ROTULO_FINAL.format(prazo=prazo)}: {_base_brl(final)}")
    blocos.append(COMO_APROVEITAR + "\n" + "\n".join(f"{n}. {p}" for n, p in enumerate(passos, 1)))
    blocos += fechamento
    blocos.append(_base.assinatura_texto())

    return {
        "assunto": ASSUNTO.format(pct=pct_txt, identificacao=_base.identificacao_assunto(clientes)),
        "html": _base.documento(TITULO.format(pct=pct_txt), ROTULO, corpo_html,
                                PREHEADER.format(pct=pct_txt, prazo=prazo)),
        "texto": "\n\n".join(blocos) + "\n",
    }


def resumo_previa(previa, campanha):
    """A prévia com o valor de cada e-mail: saldo, desconto e valor final."""
    import json
    import pandas as pd

    pct = _pct(campanha)
    linhas = []
    for l in previa.to_dict("records"):
        saldo, desconto, final = totais(json.loads(l["clientes_json"]), pct)
        linhas.append({"chave": l["chave"], "nome": l["nome"], "qtd_cadastros": l["qtd_cadastros"],
                       "saldo": saldo, "desconto": desconto, "valor_final": final,
                       "para": l["para"]})
    df = pd.DataFrame(linhas)
    if len(df):
        print(f"{len(df)} e-mail(s): saldo {_base_brl(df['saldo'].sum())}, desconto "
              f"{_base_brl(df['desconto'].sum())}, a receber à vista {_base_brl(df['valor_final'].sum())}.")
    return df
