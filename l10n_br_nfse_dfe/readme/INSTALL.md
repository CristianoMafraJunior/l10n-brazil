Este módulo requer:

1. **Dependências Odoo:**
   * `l10n_br_fiscal_dfe` (framework de distribuição abstrato)
   * `l10n_br_fiscal_certificate` (certificado A1 da empresa, usado para autenticação mTLS com o ADN)

2. **Dependências Python:**
   * `brazilfiscalreport`, usado para gerar o PDF (DANFSe). As demais dependências (`requests`, `erpbrasil.assinatura`) já vêm transitivamente de `l10n_br_fiscal_dfe` e `l10n_br_fiscal_certificate`.

## Configuração pré-requisito

1. Acesse o cadastro de **Empresas** e faça o upload de um **certificado digital A1** válido (aba de certificados).
2. Antes de habilitar a busca automática (cron), valide manualmente pelo menos uma consulta específica por NSU contra o ambiente desejado (produção ou homologação) para confirmar que o certificado está correto.
