# Copyright 2026 Cristiano Mafra Junior
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Monitor de NFS-e (DF-e Nacional)",
    "summary": """
    Monitor incoming NFS-e documents via the ADN (Ambiente de Dados
    Nacional) distribution API, reusing the generic DF-e engine.
    """,
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Cristiano Mafra Junior, Odoo Community Association (OCA)",
    "maintainers": ["CristianoMafraJunior"],
    "website": "https://github.com/OCA/l10n-brazil",
    "depends": ["l10n_br_fiscal_dfe", "l10n_br_fiscal_certificate"],
    "data": [
        "data/ir_cron.xml",
        "views/nfse_dfe_views.xml",
        "views/res_company_view.xml",
    ],
    "external_dependencies": {
        "python": ["brazilfiscalreport"],
    },
    "development_status": "Alpha",
}
