"""
Aviso de unificação das mensalidades de aluguel e licenciamento.

Comunicado informativo: não cobra, não tem prazo, não pede ação do cliente.
Um e-mail pode cobrir vários cadastros (mesmos destinatários) e lista todos no
quadro "Cadastros contemplados", logo depois do primeiro parágrafo.

O TEXTO está nas constantes abaixo, como veio do financeiro, para ser editado
sem mexer na montagem. **assim** vira negrito no HTML.

Quem recebe: contato do cadastro com e-mail de NF-e OU de boleto marcado — é
exatamente o documento que muda com a unificação.
"""

from . import _base

NOME = "Aviso de unificação das mensalidades"
FLAGS_CONTATO = ("recebeEmailNfe", "recebeEmailBoleto")
PARAMETROS = {}

ASSUNTO = "Unificação das mensalidades de aluguel e licenciamento – ctasmart – {identificacao}"
ROTULO = "Comunicado financeiro"
TITULO = "Unificação das mensalidades"
PREHEADER = ("A partir do próximo ciclo de faturamento, as mensalidades de aluguel e "
             "licenciamento serão unificadas.")

SAUDACAO = "Prezado cliente,"

PARAGRAFOS = [
    "Informamos que, a partir do próximo ciclo de faturamento, as mensalidades referentes "
    "ao aluguel e ao licenciamento serão unificadas por CNPJ e/ou por contrato jurídico.",

    "Essa mudança visa simplificar sua gestão financeira, oferecendo mais transparência, "
    "facilidade de conferência e controle nos pagamentos.",

    "Ressaltamos que **os valores contratados permanecem inalterados**, tratando-se apenas "
    "de uma otimização no modelo de faturamento.",

    "Permanecemos à disposição para eventuais esclarecimentos.",
]


def montar(clientes: list, campanha) -> dict:
    if not clientes:
        raise ValueError("nenhum cadastro para montar o e-mail.")

    corpo_html = "\n".join([
        _base.paragrafos_html([SAUDACAO, PARAGRAFOS[0]]),
        _base.bloco_cadastros_html(clientes),
        _base.paragrafos_html(PARAGRAFOS[1:]),
    ])
    texto = "\n\n".join([
        SAUDACAO,
        _base.paragrafos_texto(PARAGRAFOS[:1]),
        _base.lista_cadastros_texto(clientes),
        _base.paragrafos_texto(PARAGRAFOS[1:]),
        _base.assinatura_texto(),
    ]) + "\n"

    return {
        "assunto": ASSUNTO.format(identificacao=_base.identificacao_assunto(clientes)),
        "html": _base.documento(TITULO, ROTULO, corpo_html, PREHEADER),
        "texto": texto,
    }
