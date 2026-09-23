# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Monitor de NFS-e (DF-e Nacional)",
    "summary": """
    Monitor incoming NFS-e documents via the ADN (Ambiente de Dados
    Nacional) distribution API, reusing the generic DF-e engine.
    """,
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Engenere, Odoo Community Association (OCA)",
    "maintainers": ["CristianoMafraJunior"],
    "website": "https://github.com/OCA/l10n-brazil",
    # NOTE(draft): we depend on l10n_br_fiscal_certificate directly
    # (rather than pulling it in transitively via l10n_br_nfe, which we
    # deliberately do NOT depend on) because the ADN client needs the
    # company's A1 certificate for mTLS. We are NOT depending on
    # l10n_br_nfse_nacional / l10n_br_nfse: this module only pulls and
    # stores the raw NFS-e payloads by NSU, it does not import them
    # into a fiscal document.
    "depends": ["l10n_br_fiscal_dfe", "l10n_br_fiscal_certificate"],
    "data": [
        # Data
        "data/ir_cron.xml",
        # Views
        "views/nfse_dfe_views.xml",
        "views/res_company_view.xml",
    ],
    "external_dependencies": {
        # Used to generate the DANFSe PDF (make_pdf), same library and
        # pattern l10n_br_nfe_dfe already uses for the NF-e's DANFE.
        # Validated live (2026-09-23) against a real document's XML.
        "python": ["brazilfiscalreport"],
    },
    "development_status": "Alpha",
}
