# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Tests for DANFSe generation (``make_pdf``).

The underlying ``brazilfiscalreport.danfse.Danfse`` class itself was
validated live (2026-09-23) against a real production document's
stored XML — it produced a valid 85KB PDF on the first try. These
tests mock ``Danfse`` (no need to re-render a real PDF on every test
run) and focus on the surrounding logic: attachment creation, the
returned action, and error handling."""

import base64
from unittest import mock

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from .. import models as nfse_dfe_models


class TestDfeDocumentMakePdf(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("l10n_br_base.empresa_lucro_presumido")
        cls.Document = cls.env["l10n_br_fiscal_dfe.document"]
        cls.Dfe = cls.env["l10n_br_fiscal_dfe.dfe"]

    def _create_complete_nfse_document(self):
        document = self.Document.sudo().create(
            {
                "access_key": "5" * 50,
                "company_id": self.company.id,
                "fiscal_type": "nfse",
            }
        )
        attachment = self.env["ir.attachment"].create(
            {
                "name": "NFSe_test.xml",
                "datas": base64.b64encode(b"<NFSe>mock</NFSe>"),
            }
        )
        dfe = self.Dfe.sudo().create(
            {
                "access_key": document.access_key,
                "nsu": "000000000000001",
                "company_id": self.company.id,
                "fiscal_type": "nfse",
                "document_type_dfe": "complete",
                "attachment_id": attachment.id,
            }
        )
        document.sudo().dfe_ids = [(4, dfe.id)]
        return document

    def test_make_pdf_creates_attachment_and_returns_url_action(self):
        document = self._create_complete_nfse_document()

        fake_pdf_bytes = b"%PDF-1.4 fake"
        with mock.patch.object(nfse_dfe_models.dfe_document, "Danfse") as MockDanfse:
            instance = MockDanfse.return_value
            instance.output.side_effect = lambda buf: buf.write(fake_pdf_bytes)
            result = document.make_pdf()

        MockDanfse.assert_called_once()
        self.assertEqual(result["type"], "ir.actions.act_url")
        self.assertIn("/web/content/", result["url"])
        self.assertIn(".pdf?download=true", result["url"])

        pdf_attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "l10n_br_fiscal_dfe.document"),
                ("mimetype", "=", "application/pdf"),
            ],
            limit=1,
            order="id desc",
        )
        self.assertTrue(pdf_attachment)
        self.assertIn(document.access_key, pdf_attachment.name)
        self.assertEqual(
            base64.b64decode(pdf_attachment.with_context(bin_size=False).datas),
            fake_pdf_bytes,
        )

    def test_make_pdf_without_complete_dfe_raises_user_error(self):
        document = self.Document.sudo().create(
            {
                "access_key": "6" * 50,
                "company_id": self.company.id,
                "fiscal_type": "nfse",
            }
        )
        with self.assertRaises(UserError):
            document.make_pdf()

    def test_make_pdf_delegates_for_other_fiscal_types(self):
        document = self.Document.sudo().create(
            {
                "access_key": "7" * 44,
                "company_id": self.company.id,
                "fiscal_type": "cte",
            }
        )
        with self.assertRaises(NotImplementedError):
            document.make_pdf()

    def test_make_pdf_without_library_raises_user_error(self):
        document = self._create_complete_nfse_document()
        with mock.patch.object(nfse_dfe_models.dfe_document, "Danfse", None):
            with self.assertRaises(UserError):
                document.make_pdf()
