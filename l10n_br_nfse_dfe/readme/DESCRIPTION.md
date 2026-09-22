# Monitor de NFS-e (DF-e Nacional)

**Status: Alpha.** Validado com uma consulta real (mTLS + certificado
A1) contra o ambiente de produção restrita (homologação) da ADN em
22/09/2026. O formato de resposta, a URL e a autenticação estão
confirmados. O cron de consulta continua **desativado por padrão**
até haver mais uso em produção — veja "O que ainda não foi validado"
abaixo pra saber exatamente o que falta.

Este módulo implementa o monitoramento de **NFS-e (Nota Fiscal de
Serviço Eletrônica) de terceiros** emitidas contra o CNPJ da sua
empresa, consultando o Ambiente de Dados Nacional (ADN) do Sistema
Nacional NFS-e.

Ele estende o framework abstrato `l10n_br_fiscal_dfe` (o mesmo usado
pelo `l10n_br_nfe_dfe` para NF-e), reaproveitando toda a engine
genérica de paginação por NSU, log de distribuição, painel (banner) e
agendamento — a única peça nova é o cliente HTTP que fala com a API
REST/mTLS do ADN.

## Escopo deliberadamente reduzido

Diferente do `l10n_br_nfe_dfe`, este módulo **não importa** o XML
recebido para um documento fiscal completo do Odoo. Ele consulta, baixa
o XML bruto e o agrupa em `l10n_br_fiscal_dfe.document` quando consegue
achar a chave de acesso no payload (`_dfe_create_from_NFSe`) — sem
gerar lançamento/despesa. Por isso, ao contrário do NF-e, **não
depende de nenhum módulo de emissão** (`l10n_br_nfse_nacional` ou
`l10n_br_nfse`).

## O que já foi confirmado (consulta real em 22/09/2026)

- URL: `https://adn.producaorestrita.nfse.gov.br/contribuintes/DFe/{NSU}`
  (homologação) / `https://adn.nfse.gov.br/contribuintes/DFe/{NSU}`
  (produção).
- Autenticação mTLS com certificado A1 funciona como esperado.
- HTTP 404 = nenhum documento, com corpo JSON
  `{"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": [], ...}`.
- Os documentos (quando existem) vêm dentro de uma lista `LoteDFe` — ou
  seja, uma chamada pode retornar mais de um documento, não
  necessariamente um por NSU como o manual sugeria.
- O parâmetro `cnpjConsulta` existe, mas só deve ser usado pra
  consultar um CNPJ diferente do certificado (caso matriz/filial) — se
  usado com um CNPJ que não compartilha a raiz do certificado, a API
  responde `400` com o código `E2243`. Por isso o módulo **não envia
  esse parâmetro por padrão**.
- Ao consultar em Produção (`adn.nfse.gov.br`) a partir de um ambiente
  de desenvolvimento sem IP liberado, a conexão é recusada — parece
  haver controle de acesso por IP nesse ambiente, diferente da
  homologação. Teste em produção só a partir de uma rede já habilitada
  junto à Receita Federal.

## O que ainda não foi validado

Nunca vimos um `LoteDFe` não vazio (a empresa de teste não tinha
documentos em homologação), então o formato exato de cada item da
lista — em especial o nome do campo que carrega o XML
(gzip+base64) — continua sendo uma suposição. Veja os comentários
`TODO(adn)` em `models/adn_dfe_client.py`.
