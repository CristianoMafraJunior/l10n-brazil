# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""DANFSe generation via ``brazilfiscalreport`` (same library and same
pattern ``l10n_br_nfe_dfe`` already uses for the NF-e's DANFE).

Validated live (2026-09-23) against a real production document's
stored XML: ``Danfse(xml=xml_bytes).output(buf)`` produced a valid
85KB PDF on the first try, no adjustments needed.
"""

import base64
from io import BytesIO

from odoo import _, models
from odoo.exceptions import UserError

try:
    from brazilfiscalreport.danfse import Danfse
except ImportError:
    Danfse = None


class L10nBrFiscalDfeDocument(models.Model):
    _inherit = "l10n_br_fiscal_dfe.document"

    def make_pdf(self):
        if self.fiscal_type != "nfse":
            return super().make_pdf()
        self = self.sudo()
        complete = self._get_complete_dfe()
        if not complete or not complete.attachment_id:
            raise UserError(_("No complete DF-e found."))
        if Danfse is None:
            raise UserError(
                _(
                    "The 'brazilfiscalreport' Python library is not "
                    "installed — DANFSe generation is unavailable."
                )
            )

        xml_bytes = base64.b64decode(
            complete.attachment_id.with_context(bin_size=False).datas
        )
        danfse = Danfse(xml=xml_bytes)
        buf = BytesIO()
        danfse.output(buf)

        pdf_att = self.env["ir.attachment"].create(
            {
                "name": f"DANFSE_{complete.access_key}.pdf",
                "datas": base64.b64encode(buf.getvalue()),
                "res_model": self._name,
                "res_id": complete.id,
                "mimetype": "application/pdf",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{pdf_att.id}?download=true",
            "target": "self",
        }
