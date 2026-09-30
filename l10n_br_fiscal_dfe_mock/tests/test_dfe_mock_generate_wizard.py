# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3 or later (http://www.gnu.org/licenses/agpl)

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestDfeMockGenerateWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("l10n_br_base.empresa_simples_nacional")

    def setUp(self):
        super().setUp()
        self.env["dfe.mock.nsu"].sudo().search(
            [("company_id", "=", self.company.id)]
        ).unlink()

    def _make_wizard(self, **vals):
        vals.setdefault("company_id", self.company.id)
        return self.env["dfe.mock.generate.wizard"].create(vals)

    def test_no_type_selected_raises(self):
        wizard = self._make_wizard(
            generate_res_nfe=False,
            generate_proc_nfe=False,
            generate_res_evento=False,
            generate_proc_evento_nfe=False,
            generate_nfse=False,
        )
        with self.assertRaises(UserError):
            wizard.action_generate()

    def test_generate_nfse_only(self):
        wizard = self._make_wizard(
            quantity=3,
            generate_res_nfe=False,
            generate_proc_nfe=False,
            generate_nfse=True,
        )
        wizard.action_generate()

        records = self.env["dfe.mock.nsu"].search(
            [("company_id", "=", self.company.id)]
        )
        self.assertEqual(len(records), 3)
        self.assertTrue(all(r.fiscal_type == "nfse" for r in records))
        self.assertTrue(all(r.schema_type == "NFSe" for r in records))
        self.assertTrue(all(len(r.access_key) == 50 for r in records))
        self.assertTrue(all("<NFSe" in r.xml_content for r in records))

    def test_generate_nfe_and_nfse_share_nsu_sequence(self):
        """NF-e and NFS-e mocks share one NSU counter per company, same
        as real ADN/SEFAZ NSUs are independent counters but this
        module's pool intentionally keeps a single sequence."""
        wizard = self._make_wizard(
            quantity=2,
            generate_res_nfe=True,
            generate_proc_nfe=False,
            generate_nfse=True,
        )
        wizard.action_generate()

        records = self.env["dfe.mock.nsu"].search(
            [("company_id", "=", self.company.id)], order="nsu asc"
        )
        self.assertEqual(len(records), 4)
        nsus = [int(r.nsu) for r in records]
        self.assertEqual(nsus, sorted(nsus))
        self.assertEqual(len(set(nsus)), 4)
