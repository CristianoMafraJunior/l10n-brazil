# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""DRAFT: NFS-e implementation of the generic DF-e distribution engine.

See ``adn_dfe_client.py`` for the parts of this integration that are
still guesses pending validation against the real ADN Swagger.
"""

import logging

from lxml import etree

from odoo import api, fields, models

from odoo.addons.l10n_br_fiscal_dfe.constants.dfe import (
    DFE_ENVIRONMENT_DEFAULT,
    DFE_ENVIRONMENTS,
)

from .adn_dfe_client import AdnDfeClient

_logger = logging.getLogger(__name__)

# TODO(adn): namespace-agnostic, best-effort candidates for the access
# key element in the NFS-e Nacional XML — we don't have the real XSD.
# Every other document type in this ecosystem (NF-e, CT-e, MDF-e) names
# it "ch<Doc>" (chNFe, chCTe, chMDFe...), not the full word "chave", so
# that's the primary hint; "chave" is kept as a secondary fallback for
# more verbose naming. Replace with a proper lookup (ideally via
# nfelib.nfse bindings) once the schema is confirmed.
_ACCESS_KEY_HINTS = ("ch", "chave")
_ACCESS_KEY_MIN_LENGTH = 40


class ResCompany(models.Model):
    """NFS-e (ADN) implementation of the generic DF-e distribution engine."""

    _inherit = "res.company"

    # ── NFS-e DF-e configuration (typed fields convention) ─────────────

    nfse_environment = fields.Selection(
        selection=DFE_ENVIRONMENTS,
        default=DFE_ENVIRONMENT_DEFAULT,
        string="NFS-e ADN Environment",
    )

    nfse_last_nsu = fields.Char(string="NFS-e Last NSU", size=25, default="0")

    nfse_max_nsu = fields.Char(string="NFS-e Max NSU", readonly=True)

    nfse_dfe_last_query = fields.Datetime(string="NFS-e DF-e Last Query")

    nfse_dfe_last_status = fields.Char(string="NFS-e DF-e Last Status", readonly=True)

    nfse_dfe_last_status_code = fields.Char(
        string="NFS-e DF-e Last Status Code", readonly=True
    )

    nfse_dfe_next_query = fields.Datetime(
        string="NFS-e Next Scheduled Query",
        help="NFS-e DF-e distribution (ADN) will not be queried before " "this time.",
    )

    nfse_auto_fetch = fields.Boolean(
        default=False,
        string="Auto-fetch NFS-e DF-e",
        help="Periodically queries the ADN distribution API for new " "NFS-e documents",
    )

    # ── Generic engine hooks ────────────────────────────────────────────

    def _dfe_get_processor(self, fiscal_type):
        if fiscal_type != "nfse":
            return super()._dfe_get_processor(fiscal_type)
        self.ensure_one()
        return AdnDfeClient(self)

    def _dfe_cron_xmlid(self, fiscal_type):
        if fiscal_type == "nfse":
            return "l10n_br_nfse_dfe.ir_cron_search_nfse_dfe_documents"
        return super()._dfe_cron_xmlid(fiscal_type)

    def _dfe_document_action_xmlid(self, fiscal_type):
        if fiscal_type == "nfse":
            return "l10n_br_nfse_dfe.action_nfse_dfe_document"
        return super()._dfe_document_action_xmlid(fiscal_type)

    # ── NFS-e specific actions ──────────────────────────────────────────

    def nfse_dfe_search_documents(self):
        for record in self:
            record._dfe_document_distribution("nfse")

    @api.model
    def _cron_nfse_dfe_search_documents(self):
        return self._cron_dfe_search_documents("nfse")

    @api.model
    def action_banner_search_all_nfse(self):
        """Called from the NFS-e banner button — delegates to current
        company."""
        company = self.env.company
        result = company.action_document_distribution("nfse")
        return result or {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def action_banner_specific_search_nfse(self):
        """Called from the NFS-e banner button — delegates to current
        company."""
        return self.env.company.action_search_specific("nfse")

    # ── Schema processor ─────────────────────────────────────────────────

    def _dfe_create_from_NFSe(self, root, nsu, fiscal_type="nfse"):  # noqa: N802
        """Group the downloaded NFS-e under a ``l10n_br_fiscal_dfe.document``
        when we can find its access key, instead of leaving it as a bare
        ``l10n_br_fiscal_dfe.dfe`` record with no XML content indexed.

        This is *not* the "import" step (no ``l10n_br_fiscal.document``
        / accounting entry is created) — it's the same lightweight
        tracking ``l10n_br_nfe_dfe`` does for every schema type, kept
        here so the "NFS-e de Terceiros" list isn't permanently empty.
        If the access key can't be found, this degrades gracefully to
        the same ungrouped behavior the generic engine's own fallback
        already has.
        """
        DfeRecord = self.env["l10n_br_fiscal_dfe.dfe"].sudo()
        dfe_record = DfeRecord.create(
            {"nsu": nsu, "company_id": self.id, "fiscal_type": fiscal_type}
        )

        access_key = self._nfse_find_access_key(root)
        if access_key:
            dfe_document = self._dfe_get_or_create_document(access_key, fiscal_type)
            dfe_document.sudo().dfe_ids = [(4, dfe_record.id)]
        else:
            _logger.warning(
                "NFS-e DF-e: could not find an access key in the payload "
                "for NSU %s, storing ungrouped (see TODO(adn) in "
                "res_company.py)",
                nsu,
            )

        return dfe_record

    @api.model
    def _nfse_find_access_key(self, root):
        try:
            for el in root.iter():
                if not isinstance(el.tag, str):
                    continue
                local_name = etree.QName(el).localname.lower()
                is_candidate = (
                    local_name.startswith(_ACCESS_KEY_HINTS[0])
                    or _ACCESS_KEY_HINTS[1] in local_name
                )
                if not is_candidate:
                    continue
                text = (el.text or "").strip()
                if text.isdigit() and len(text) >= _ACCESS_KEY_MIN_LENGTH:
                    return text
        except Exception:
            _logger.exception("NFS-e DF-e: error looking for the access key")
        return None
