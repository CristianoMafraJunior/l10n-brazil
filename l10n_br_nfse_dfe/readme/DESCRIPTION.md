# Monitor de NFS-e (DF-e Nacional)

Este módulo implementa o monitoramento de **NFS-e (Nota Fiscal de Serviço Eletrônica) de terceiros** emitidas contra o CNPJ da sua empresa, consultando o Ambiente de Dados Nacional (ADN) do Sistema Nacional NFS-e.

Ele estende o framework abstrato `l10n_br_fiscal_dfe` (o mesmo usado pelo `l10n_br_nfe_dfe` para NF-e), reaproveitando toda a engine genérica de paginação por NSU, log de distribuição, painel (banner) e agendamento — a única peça nova é o cliente HTTP que fala com a API REST/mTLS do ADN.

## Escopo deliberadamente reduzido

* **Não importa** o XML recebido para um documento fiscal completo do Odoo. Ele consulta, baixa o XML bruto e o agrupa em `l10n_br_fiscal_dfe.document` quando consegue achar a chave de acesso no payload — sem gerar lançamento/despesa.
* **Não depende** de nenhum módulo de emissão (`l10n_br_nfse_nacional` ou `l10n_br_nfse`), ao contrário do que acontece com NF-e.
* **Geração de DANFSe:** o PDF do documento pode ser gerado a partir do XML armazenado, usando a biblioteca `brazilfiscalreport` (mesma lib e padrão que o `l10n_br_nfe_dfe` já usa para o DANFE de NF-e).

## Confirmado contra o ambiente real do ADN

* URL: `https://adn.producaorestrita.nfse.gov.br/contribuintes/DFe/{NSU}` (homologação) / `https://adn.nfse.gov.br/contribuintes/DFe/{NSU}` (produção).
* Autenticação mTLS com certificado A1 funciona como esperado.
* HTTP 404 = nenhum documento, com corpo JSON `{"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": [], ...}`.
* Os documentos vêm dentro de uma lista `LoteDFe`, com o XML no campo `ArquivoXml` (gzip+base64) — uma chamada pode retornar mais de um documento.
* A chave de acesso não vem em um elemento próprio: está embutida no atributo `Id` do elemento raiz (`<infNFSe Id="NFS<chave>">`).
* O parâmetro `cnpjConsulta` existe, mas só deve ser usado para consultar um CNPJ diferente do certificado (caso matriz/filial) — se usado com um CNPJ que não compartilha a raiz do certificado, a API responde `400` com o código `E2243`. Por isso o módulo **não envia esse parâmetro por padrão**.
* A numeração de NSU do ADN tem buracos reais (NSUs que nunca resolvem a um documento para o CNPJ consultado) — a sincronização tolera esses buracos em vez de travar neles.

## O que ainda não foi validado

* Se o ADN limita o tamanho da lista `LoteDFe` por chamada, e em qual valor.
* O formato exato esperado para o NSU na URL (usamos um inteiro simples, que funcionou nos testes reais; não confirmamos se um formato zero-padded também é aceito).
* Consultas matriz/filial via `cnpjConsulta` (não implementadas).
* Busca específica por chave de acesso (o ADN não expõe esse endpoint pela distribuição, só por NSU).

Veja os comentários `TODO(adn)` em `models/adn_dfe_client.py` para o estado exato de cada ponto em aberto.
