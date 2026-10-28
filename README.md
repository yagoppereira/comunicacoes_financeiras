# Comunicações financeiras — ctasmart

Envio de comunicados para clientes a partir de `contato.financeiro@ctasmart.com.br`,
com os destinatários tirados **só do cadastro do CIGAM no DW**
(`bronze.cigam__empresas.contatos_json`). Sem planilha de contatos, sem vendedor em cópia.

Segue o desenho do aviso de bloqueio (`Cta-Link2pump-Block-Routine`), mais enxuto:
não há títulos, encargos nem congelamento em planilha. Ficaram as proteções de envio.

Primeiro comunicado: **aviso de unificação das mensalidades** de aluguel e licenciamento
(`comunicacoes_financeiras/modelos/unificacao_contratos.py`).

## Ciclo

| Passo | Função | Consulta o DW? |
|---|---|---|
| Ler a lista | `fluxo.ler_lista_planilha(link_do_xlsx)` | não |
| Preparar | `fluxo.preparar(bq, c, lista)` | sim |
| Conferir | humano: a prévia e quem NÃO vai receber | não |
| Ver o e-mail | `fluxo.previa_email(c, previa)` | não |
| Testar | `fluxo.disparar(...)` com `Campanha.teste` | não |
| Enviar | `fluxo.disparar(...)` com `Campanha.producao` | não |

`disparar()` manda para os destinatários da **prévia**, que foi a que você conferiu.

## Quem recebe

Cada modelo diz quais marcações do contato valem (`FLAGS_CONTATO`). Na unificação, basta
`recebeEmailNfe` **ou** `recebeEmailBoleto` = S, porque é esse o documento que muda.

Ficam de fora, e aparecem na lista de rejeitados com o motivo:

- divisão 13 (CLIENTE LOCAL): é onde o equipamento está instalado, não quem paga;
- divisões que não são de cliente (fornecedor, colaborador...);
- 000679 LINK2PUMP (intercompany);
- CPF/CNPJ com mais de um cadastro de cliente: informe o código;
- cadastro sem e-mail válido, ou com todos os e-mails marcados N.

Cadastros com **exatamente os mesmos destinatários** recebem um e-mail só, listando todos
(ex.: grupo com 6 obras e o mesmo financeiro). Quem lê a mensagem já é contato de cada
cadastro listado nela.

## Notebook (Colab)

```python
!git clone https://github.com/yagoppereira/comunicacoes_financeiras.git
!pip install -q -r comunicacoes_financeiras/requirements.txt
import sys; sys.path.insert(0, "comunicacoes_financeiras")

from comunicacoes_financeiras import fluxo, envio
from comunicacoes_financeiras.campanha import Campanha

bq = fluxo.conectar_colab()

# Lista dos clientes afetados: coluna "COD CIGAM" da aba "lista comunicado".
# Aceita o link do Drive (arquivo compartilhado com você), o ID ou um caminho local.
lista = fluxo.ler_lista_planilha(
    "https://docs.google.com/spreadsheets/d/111fwG0ouHLTcxOFmzR2IhH0ADLcLy6Xf/edit",
    aba="lista comunicado", coluna="COD CIGAM")
# ou, colando à mão: lista = """000479\n3106\n76.538.412/0001-41"""

PARAM = dict(id_campanha="UNIF-2026-11-A", modelo="unificacao_contratos")

c = Campanha.ensaio(**PARAM)
previa, resolucao = fluxo.preparar(bq, c, lista)   # imprime quem NÃO vai receber e por quê
previa                                              # confira
fluxo.previa_email(c, previa)                       # veja o e-mail
```

Log: no Colab o disco some quando o runtime cai. Monte o Drive e use um CSV lá, ou uma aba
do Sheets:

```python
from google.colab import drive; drive.mount("/content/drive")
registro = envio.RegistroCSV("/content/drive/MyDrive/comunicacoes_financeiras/log.csv")
# ou: envio.RegistroPlanilha(gspread_client.open_by_key("...").worksheet("Log"))
```

Teste — tudo vai só para você, com os destinatários reais impressos no topo:

```python
from google.colab import userdata
enviar = fluxo.criar_enviador(usuario="contato.financeiro@ctasmart.com.br",
                              senha_app=userdata.get("SMTP_FINANCEIRO"))   # Secrets do Colab
fluxo.disparar(Campanha.teste(**PARAM, para="yago.gutterres@ctasmart.com.br"),
               previa, enviar, registro)
```

Para valer:

```python
fluxo.disparar(Campanha.producao(**PARAM), previa, enviar, registro)
```

Na lista, código repetido conta uma vez (o resumo diz quantos). Código lido como número
pela planilha (`5115.0`) é tratado como `005115`.

Sem `Campanha.teste` ou `Campanha.producao` nada sai: o default é o ensaio, e uma campanha
de produção sem `confirmo_producao=True` é recusada. O log é por código de cliente:
reexecutar continua de onde parou e não manda duas vezes para o mesmo cadastro.

### Sobre a conta que envia

O SMTP do Gmail precisa de uma conta com senha de app (exige verificação em duas etapas).

- Se `contato.financeiro@` for uma conta própria, autentique com ela (exemplo acima).
- Se for um grupo/caixa compartilhada sem login, autentique com a sua conta
  (`usuario="seu.email@ctasmart.com.br"`) e cadastre `contato.financeiro@` em
  Gmail → Configurações → Contas → "Enviar e-mail como". Sem isso o Gmail troca o
  remetente pela sua conta. O Reply-To já aponta para `contato.financeiro@`.

O teto diário padrão é 450 destinatários (Gmail comum corta em 500, Workspace em 2.000).
Ao bater o teto, a fila fica pendente para a próxima execução. Numa conta Workspace dá
para subir, ex.: `Campanha.producao(**PARAM, teto_diario=1500)`.

## Visual

Segue o brandbook 2026 do marketing (`comunicacoes_financeiras/modelos/_base.py`):
cabeçalho Night com o logo branco e o grafismo do losango vazado, rótulo em Fuel Green,
título em Poppins, texto em DM Sans, quadro de cadastros com barra Cobalt, assinatura com
barra Fuel Green, rodapé Night. O nome da marca é sempre `ctasmart`, minúsculo.

- O cabeçalho é imagem (`comunicacoes_financeiras/assets/cabecalho.png`), embutida no
  e-mail: cliente de e-mail não desenha SVG nem rotação em CSS. Para mudar, edite
  `assets/cabecalho.html` e rode `node comunicacoes_financeiras/assets/gerar_cabecalho.js`
  (Playwright para Node).
- Poppins e DM Sans aparecem no Apple Mail, no iOS e no Outlook para Mac. O Gmail ignora
  fonte externa e mostra Helvetica/Arial; o resto do layout fica igual.
- `previa_email()` mostra o cabeçalho de verdade no notebook (troca o `cid:` pela imagem).

## Novo comunicado

Copie `comunicacoes_financeiras/modelos/unificacao_contratos.py`, troque `ASSUNTO`, `TITULO`,
`PARAGRAFOS` (`**assim**` vira negrito), `FLAGS_CONTATO` e `PARAMETROS`, e registre em
`comunicacoes_financeiras/modelos/__init__.py`. A moldura visual, a lista, os contatos, a
prévia, o envio e o log são os mesmos.

## Testes

```
python -m unittest discover -s comunicacoes_financeiras/tests -t .
```

Cobrem lista (inclusive leitura do .xlsx), contatos, agrupamento, texto, marca e fila. SMTP, BigQuery e Sheets não estão
cobertos (dependem de credencial): faça o teste redirecionado com 2 ou 3 clientes antes de
enviar para valer.
