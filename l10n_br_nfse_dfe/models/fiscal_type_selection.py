# Copyright 2026 Cristiano Mafra Junior
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class L10nBrFiscalDfeDfe(models.Model):
    _inherit = "l10n_br_fiscal_dfe.dfe"

    fiscal_type = models.fields.Selection(selection_add=[("nfse", "NFS-e")])
    access_key = models.fields.Char(index=True, size=None)


class L10nBrFiscalDfeDistributionLog(models.Model):
    _inherit = "l10n_br_fiscal_dfe.distribution_log"

    fiscal_type = models.fields.Selection(selection_add=[("nfse", "NFS-e")])


class DfeSpecificSearchWizard(models.TransientModel):
    _inherit = "dfe.specific.search.wizard"

    fiscal_type = models.fields.Selection(
        selection_add=[("nfse", "NFS-e")],
        ondelete={"nfse": "cascade"},
    )
