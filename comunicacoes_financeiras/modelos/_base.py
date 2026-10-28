"""
Moldura visual comum a todos os comunicados, no brandline 2026 do marketing
(BRANDBOOK_2026): cabeçalho Night com o logo branco e o grafismo do losango,
cartão branco com rótulo e título, barra de cor, rodapé Night.

POR QUE O CABEÇALHO É IMAGEM
Cliente de e-mail não renderiza SVG nem rotação em CSS: o losango vazado só
chega igual para todo mundo como imagem. Ela vai EMBUTIDA por cid: (ver
envio.criar_enviador_smtp) e é gerada por assets/gerar_cabecalho.js.

FONTES
O brandbook pede Poppins (títulos) e DM Sans (texto). O <link> do Google Fonts
funciona no Apple Mail, iOS e Outlook para Mac; o Gmail o descarta e cai no
fallback (Helvetica/Arial). Não há como forçar fonte no Gmail sem virar o
texto em imagem, o que estragaria leitura, busca e acessibilidade.

NOME DA MARCA
"ctasmart", sempre minúsculo — inclusive no assunto e na assinatura.

TEXTO DOS MODELOS
Os modelos escrevem os parágrafos como texto simples; **assim** vira negrito
no HTML e some na versão texto.
"""

import html
import re
from pathlib import Path

REMETENTE_EMAIL = "contato.financeiro@ctasmart.com.br"
REMETENTE_NOME = "ctasmart Financeiro"
ASSINATURA_NOME = "Equipe Financeira"
SITE = "www.ctasmart.com.br"
ASSINATURA_FRASE = "ctasmart · controle inteligente de combustíveis"

ASSETS = Path(__file__).resolve().parents[1] / "assets"
CID_CABECALHO = "cabecalho_ctasmart"
IMAGENS = {CID_CABECALHO: str(ASSETS / "cabecalho.png")}   # cid -> arquivo

# Paleta do brandbook (Sistema de cores completo).
COBALT = "#0040D0"        # principal: headers, CTAs, links
COBALT_5 = "#EBF0FE"      # fundos suaves
COBALT_DARK = "#0035A8"
VERDE = "#00C389"         # acento — nunca fundo grande
VERDE_DARK = "#007352"    # texto verde sobre claro
NIGHT = "#060D1F"         # fundos premium e texto principal
NIGHT_LIGHT = "#1A2540"
SLATE_700 = "#3A4D72"     # texto secundário
SLATE_200 = "#B8C4DC"     # texto sobre Night
BORDA = "#E3E7EF"
OFF_WHITE = "#F2F4F8"     # fundo da página

FONTE_TITULO = "Poppins,'Helvetica Neue',Helvetica,Arial,sans-serif"
FONTE_TEXTO = "'DM Sans','Helvetica Neue',Helvetica,Arial,sans-serif"

DOCUMENTO = """<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<title>{titulo}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500&family=Poppins:wght@600;700&display=swap" rel="stylesheet">
<style>
  @media (max-width:620px) {{ .cf-pad {{ padding:28px 22px !important; }} .cf-h1 {{ font-size:21px !important; }} }}
</style>
</head>
<body style="margin:0;padding:0;background:{off_white}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{off_white};border-collapse:collapse">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;border-collapse:collapse">
<tr><td style="background:{night}"><img src="cid:{cid}" width="600" alt="link2pump ctasmart" style="display:block;width:100%;max-width:600px;height:auto;border:0"></td></tr>
<tr><td class="cf-pad" style="background:#FFFFFF;padding:36px 40px 32px;font-family:{fonte_texto};font-size:15px;line-height:1.65;color:{night_light}">
<div style="font-family:{fonte_titulo};font-size:11px;font-weight:600;letter-spacing:3px;color:{verde_dark};text-transform:uppercase">{rotulo}</div>
<h1 class="cf-h1" style="margin:8px 0 22px;font-family:{fonte_titulo};font-size:24px;line-height:1.25;font-weight:700;color:{night}">{titulo}</h1>
{corpo}
{assinatura}
</td></tr>
<tr><td style="background:{night};padding:18px 40px;font-family:{fonte_texto};font-size:12px;line-height:1.6;color:{slate_200}">
{frase}<br><a href="https://{site}" style="color:#FFFFFF;text-decoration:none">{site}</a>
</td></tr>
</table>
</td></tr></table>
</body></html>"""

ASSINATURA_HTML = """<p style="margin:26px 0 14px">Atenciosamente,</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
<tr><td style="border-left:3px solid {verde};padding:2px 0 2px 14px;font-family:{fonte_texto};font-size:13px;line-height:1.55;color:{slate_700}">
<div style="font-family:{fonte_titulo};font-size:15px;font-weight:600;color:{night}">{nome}</div>
<div>ctasmart</div>
<div><a href="mailto:{email}" style="color:{cobalt};text-decoration:none">{email}</a></div>
</td></tr></table>"""

ASSINATURA_TEXTO = "Atenciosamente,\n\n{nome}\nctasmart\n{email}\n{site}"

_NEGRITO = re.compile(r"\*\*(.+?)\*\*")


def _p_html(texto: str) -> str:
    seguro = _NEGRITO.sub(lambda m: f'<strong style="color:{NIGHT}">{m.group(1)}</strong>',
                          html.escape(texto))
    return f'<p style="margin:0 0 16px">{seguro}</p>'


def paragrafos_html(paragrafos) -> str:
    return "\n".join(_p_html(p) for p in paragrafos)


def paragrafos_texto(paragrafos) -> str:
    return "\n\n".join(_NEGRITO.sub(r"\1", p) for p in paragrafos)


def documento(titulo: str, rotulo: str, corpo_html: str, preheader: str = "") -> str:
    """Envolve o corpo do comunicado na moldura da marca."""
    return DOCUMENTO.format(
        titulo=html.escape(titulo), rotulo=html.escape(rotulo), corpo=corpo_html,
        preheader=html.escape(preheader), assinatura=assinatura_html(),
        cid=CID_CABECALHO, frase=html.escape(ASSINATURA_FRASE), site=SITE,
        off_white=OFF_WHITE, night=NIGHT, night_light=NIGHT_LIGHT, verde_dark=VERDE_DARK,
        slate_200=SLATE_200, fonte_titulo=FONTE_TITULO, fonte_texto=FONTE_TEXTO,
    )


def assinatura_html() -> str:
    return ASSINATURA_HTML.format(
        nome=html.escape(ASSINATURA_NOME), email=REMETENTE_EMAIL, verde=VERDE,
        night=NIGHT, slate_700=SLATE_700, cobalt=COBALT,
        fonte_titulo=FONTE_TITULO, fonte_texto=FONTE_TEXTO)


def assinatura_texto() -> str:
    return ASSINATURA_TEXTO.format(nome=ASSINATURA_NOME, email=REMETENTE_EMAIL, site=SITE)


def formatar_documento(doc) -> str:
    """'7636657001241' -> '07.636.657/0012-41'. O cliente confere o CNPJ para
    saber se o e-mail é dele: número cru e sem zero à esquerda gera dúvida."""
    d = "".join(ch for ch in str(doc or "") if ch.isdigit())
    if not d:
        return ""
    if len(d) in (12, 13):      # CNPJ que perdeu o zero à esquerda numa planilha
        d = d.zfill(14)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d


def razao_social(cliente: dict) -> str:
    return (cliente.get("nome") or cliente.get("fantasia") or cliente.get("codigo") or "").strip()


def identificacao_assunto(clientes: list) -> str:
    """'RAZÃO SOCIAL - 00.000.000/0000-00' ou, com vários cadastros,
    'RAZÃO SOCIAL e mais N cadastro(s)'."""
    primeiro = clientes[0]
    if len(clientes) == 1:
        doc = formatar_documento(primeiro.get("cnpj_cpf"))
        return f"{razao_social(primeiro)} - {doc}" if doc else razao_social(primeiro)
    return f"{razao_social(primeiro)} e mais {len(clientes) - 1} cadastro(s)"


def bloco_cadastros_html(clientes: list, rotulo: str = "Cadastros contemplados") -> str:
    """Quadro com os cadastros cobertos pelo e-mail: fundo Cobalt 5% e barra de
    cor à esquerda (grafismo 05 do brandbook). <table>, não div/flex: Outlook
    ignora flexbox."""
    linhas = []
    for i, c in enumerate(clientes):
        borda = f"border-top:1px solid {BORDA};" if i else ""
        linhas.append(
            f'<tr><td style="{borda}padding:9px 0;font-family:{FONTE_TEXTO};font-size:14px;'
            f'line-height:1.4;color:{NIGHT}">{html.escape(razao_social(c))}</td>'
            f'<td align="right" style="{borda}padding:9px 0 9px 14px;font-family:{FONTE_TEXTO};'
            f'font-size:13px;color:{SLATE_700};white-space:nowrap">'
            f'{formatar_documento(c.get("cnpj_cpf")) or "—"}</td></tr>')
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;margin:4px 0 22px">'
        f'<tr><td style="background:{COBALT_5};border-left:4px solid {COBALT};padding:14px 18px">'
        f'<div style="font-family:{FONTE_TITULO};font-size:10px;font-weight:600;letter-spacing:2px;'
        f'color:{COBALT_DARK};text-transform:uppercase;margin-bottom:4px">{html.escape(rotulo)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse">{"".join(linhas)}</table>'
        f'</td></tr></table>')


def lista_cadastros_texto(clientes: list, rotulo: str = "Cadastros contemplados") -> str:
    itens = "\n".join(f"  - {razao_social(c)} - {formatar_documento(c.get('cnpj_cpf')) or 's/ documento'}"
                      for c in clientes)
    return f"{rotulo}:\n{itens}"
