Este módulo requer:

1. **Dependências Odoo:**
    * `l10n_br_fiscal_dfe` (framework de distribuição abstrato)
    * `l10n_br_fiscal_certificate` (certificado A1 da empresa, usado
      para autenticação mTLS com o ADN)

2. **Dependências Python:** nenhuma além do que `l10n_br_fiscal_dfe` e
   `l10n_br_fiscal_certificate` já exigem (`requests` já vem com o
   Odoo; `erpbrasil.assinatura` já é dependência transitiva do
   certificado).

## Configuração pré-requisito

1. Acesse o cadastro de **Empresas** e faça o upload de um
   **certificado digital A1** válido (aba de certificados).
2. Antes de ligar a busca automática, valide manualmente pelo menos uma
   consulta específica por NSU contra o ambiente de produção restrita
   (homologação) da ADN — este módulo ainda não foi testado contra o
   ambiente real.
