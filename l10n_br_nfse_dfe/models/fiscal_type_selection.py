# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class L10nBrFiscalDfeDocument(models.Model):
    _inherit = "l10n_br_fiscal_dfe.document"

    fiscal_type = models.fields.Selection(selection_add=[("nfse", "NFS-e")])

    # access_key is size=44 on the base model (NF-e/CT-e keys are
    # always 44 digits). NFS-e Nacional access keys are reportedly 50
    # characters (per third-party integration docs, not the ADN manual
    # itself) — drop the size constraint entirely rather than guess a
    # possibly-wrong exact number; this doesn't affect NF-e records.
    access_key = models.fields.Char(required=True, index=True)


class L10nBrFiscalDfeDfe(models.Model):
    _inherit = "l10n_br_fiscal_dfe.dfe"

    fiscal_type = models.fields.Selection(selection_add=[("nfse", "NFS-e")])


class L10nBrFiscalDfeDistributionLog(models.Model):
    _inherit = "l10n_br_fiscal_dfe.distribution_log"

    fiscal_type = models.fields.Selection(selection_add=[("nfse", "NFS-e")])


class DfeSpecificSearchWizard(models.TransientModel):
    _inherit = "dfe.specific.search.wizard"

    fiscal_type = models.fields.Selection(
        selection_add=[("nfse", "NFS-e")],
        ondelete={"nfse": "cascade"},
    )
