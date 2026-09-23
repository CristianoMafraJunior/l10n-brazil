# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class L10nBrFiscalDfeDocument(models.Model):
    _inherit = "l10n_br_fiscal_dfe.document"

    fiscal_type = models.fields.Selection(selection_add=[("nfse", "NFS-e")])

    # access_key is size=44 on the base model (NF-e/CT-e keys are
    # always 44 digits). NFS-e Nacional access keys are confirmed 50
    # characters (seen live, 2026-09-22, on a real production document)
    # — drop the size constraint entirely rather than hardcode 50; this
    # doesn't affect NF-e records. IMPORTANT: `size=None` must be passed
    # *explicitly* — omitting the kwarg does NOT reset it, Odoo's field
    # merging across `_inherit` keeps the base class's size=44 unless
    # a module in the chain explicitly overrides it (learned the hard
    # way: omitting it here silently truncated every NFS-e key to 44
    # chars, caught only against real production data).
    access_key = models.fields.Char(required=True, index=True, size=None)


class L10nBrFiscalDfeDfe(models.Model):
    _inherit = "l10n_br_fiscal_dfe.dfe"

    fiscal_type = models.fields.Selection(selection_add=[("nfse", "NFS-e")])

    # Same truncation issue as l10n_br_fiscal_dfe.document.access_key
    # above — this is the OTHER model with a 44-char access_key.
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
