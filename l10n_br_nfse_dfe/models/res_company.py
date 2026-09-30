# Copyright 2026 Cristiano Mafra Junior
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime, timezone

from lxml import etree

from odoo import api, fields, models

from odoo.addons.l10n_br_fiscal_dfe.constants.dfe import (
    DFE_ENVIRONMENT_DEFAULT,
    DFE_ENVIRONMENTS,
)
from odoo.addons.l10n_br_fiscal_dfe.tools import utils

from .adn_dfe_client import AdnDfeClient

_logger = logging.getLogger(__name__)
_ACCESS_KEY_ROOT_TAG = "infNFSe"
_ACCESS_KEY_ID_PREFIX = "NFS"
_ACCESS_KEY_MIN_LENGTH = 40


class ResCompany(models.Model):
    """NFS-e (ADN) implementation of the generic DF-e distribution engine."""

    _inherit = "res.company"
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

    def _dfe_create_from_NFSe(self, root, nsu, fiscal_type="nfse"):  # noqa: N802
        access_key = self._nfse_find_access_key(root)

        vals = {"nsu": nsu, "company_id": self.id, "fiscal_type": fiscal_type}
        if access_key:
            vals["access_key"] = access_key
            vals["document_type_dfe"] = "complete"

        DfeRecord = self.env["l10n_br_fiscal_dfe.dfe"].sudo()
        dfe_record = DfeRecord.create(vals)

        if access_key:
            dfe_document = self._dfe_get_or_create_document(access_key, fiscal_type)
            dfe_document.sudo().dfe_ids = [(4, dfe_record.id)]
            metadata = self._nfse_extract_metadata(root)
            if metadata:
                dfe_document._update_metadata(metadata, is_complete=True)
        else:
            _logger.warning(
                "NFS-e DF-e: could not find an access key in the payload "
                "for NSU %s, storing ungrouped",
                nsu,
            )

        return dfe_record

    @api.model
    def _nfse_find_access_key(self, root):
        try:
            for el in root.iter():
                if not isinstance(el.tag, str):
                    continue
                if etree.QName(el).localname != _ACCESS_KEY_ROOT_TAG:
                    continue
                id_attr = el.get("Id") or ""
                digits = (
                    id_attr[len(_ACCESS_KEY_ID_PREFIX) :]
                    if id_attr.upper().startswith(_ACCESS_KEY_ID_PREFIX)
                    else id_attr
                )
                if digits.isdigit() and len(digits) >= _ACCESS_KEY_MIN_LENGTH:
                    return digits
        except Exception:
            _logger.exception("NFS-e DF-e: error looking for the access key")
        return None

    @staticmethod
    def _nfse_child_by_path(root, *local_names):
        """Namespace-agnostic descent through a chain of child local
        names, e.g. ``_nfse_child_by_path(root, "infNFSe", "emit",
        "xNome")`` for ``<infNFSe><emit><xNome>``. Only ever follows
        *direct* children at each step, so it can't accidentally match
        a same-named element nested somewhere else in the document
        (e.g. <toma><xNome> or <prest><xNome> instead of <emit><xNome>).
        """
        current = root
        for local_name in local_names:
            found = None
            for child in current.iterchildren():
                if (
                    isinstance(child.tag, str)
                    and etree.QName(child).localname == local_name
                ):
                    found = child
                    break
            if found is None:
                return None
            current = found
        return current

    def _nfse_child_text(self, root, *local_names):
        el = self._nfse_child_by_path(root, *local_names)
        if el is None or not el.text:
            return None
        return el.text.strip()

    def _nfse_extract_metadata(self, root):
        vals = {}
        try:
            xnome = self._nfse_child_text(root, "infNFSe", "emit", "xNome")
            if xnome:
                vals["emitter"] = xnome

            cnpj = self._nfse_child_text(root, "infNFSe", "emit", "CNPJ")
            if cnpj:
                vals["vat"] = utils.mask_cnpj(cnpj)

            nnfse = self._nfse_child_text(root, "infNFSe", "nNFSe")
            if nnfse:
                vals["document_number"] = nnfse

            vliq = self._nfse_child_text(root, "infNFSe", "valores", "vLiq")
            if vliq:
                vals["document_amount"] = float(vliq)

            cstat = self._nfse_child_text(root, "infNFSe", "cStat")
            if cstat:
                vals["document_state"] = cstat

            serie = self._nfse_child_text(root, "infNFSe", "DPS", "infDPS", "serie")
            if serie:
                vals["serie"] = serie

            dh_emi = self._nfse_child_text(root, "infNFSe", "DPS", "infDPS", "dhEmi")
            if dh_emi:
                vals["document_emission_date"] = (
                    datetime.fromisoformat(dh_emi)
                    .astimezone(timezone.utc)
                    .replace(tzinfo=None)
                )
        except (ValueError, TypeError):
            _logger.exception("NFS-e DF-e: error extracting document metadata")
        return vals
