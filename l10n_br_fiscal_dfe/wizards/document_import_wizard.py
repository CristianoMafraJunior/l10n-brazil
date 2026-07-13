# Copyright 2026 Engenere (<https://engenere.one>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class DocumentImportWizard(models.TransientModel):
    _inherit = "l10n_br_fiscal.document.import.wizard"

    def _import_edoc(self):
        result = super()._import_edoc()
        dfe_document_id = self.env.context.get("dfe_document_id")
        if dfe_document_id and self.document_id:
            dfe_document = self.env["l10n_br_fiscal_dfe.document"].browse(
                dfe_document_id
            )
            dfe_document._compute_imported_document_id()
        return result
