# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3 or later (http://www.gnu.org/licenses/agpl)

import gzip
from unittest import mock

from odoo import fields
from odoo.tests.common import TransactionCase

from ..models.res_company import MockDfeClient

SAMPLE_RES_NFE = (
    '<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">'
    "<chNFe>35260210588201000105550010000001231000001230</chNFe>"
    "<CNPJ>10588201000105</CNPJ>"
    "<xNome>Partner Mock Ltda</xNome>"
    "<vNF>5432.10</vNF>"
    "</resNFe>"
)

ACCESS_KEY = "35260210588201000105550010000001231000001230"
NFE_DFE_PROCESSOR = (
    "odoo.addons.l10n_br_nfe_dfe.models.res_company.ResCompany._dfe_get_processor"
)

NFSE_ACCESS_KEY = "4" * 50
SAMPLE_NFSE = (
    '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
    f'<infNFSe Id="NFS{NFSE_ACCESS_KEY}">'
    "<nNFSe>2300000000054</nNFSe>"
    "<cStat>100</cStat>"
    "<emit><CNPJ>21990799000180</CNPJ><xNome>Partner NFSe Mock</xNome></emit>"
    "<valores><vLiq>269.90</vLiq></valores>"
    "</infNFSe>"
    "</NFSe>"
)


class TestDfeMockDistribution(TransactionCase):
    """Tests for the mock DF-e distribution processor on res.company."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("l10n_br_base.empresa_simples_nacional")
        cls.company.sudo().write({"dfe_mock_mode": True})

    def setUp(self):
        super().setUp()
        self.env["dfe.mock.nsu"].sudo().search(
            [("company_id", "=", self.company.id)]
        ).unlink()

    def _create_nsu(self, nsu, schema_type="resNFe", access_key=None, consumed=False):
        return self.env["dfe.mock.nsu"].create(
            {
                "nsu": nsu,
                "schema_type": schema_type,
                "xml_content": SAMPLE_RES_NFE,
                "access_key": access_key or ACCESS_KEY,
                "company_id": self.company.id,
                "consumed": consumed,
            }
        )

    def _create_nfse_nsu(self, nsu, access_key=None, consumed=False):
        return self.env["dfe.mock.nsu"].create(
            {
                "nsu": nsu,
                "fiscal_type": "nfse",
                "schema_type": "NFSe",
                "xml_content": SAMPLE_NFSE,
                "access_key": access_key or NFSE_ACCESS_KEY,
                "company_id": self.company.id,
                "consumed": consumed,
            }
        )

    # ── _dfe_get_processor ──────────────────────────────────────────────

    def test_get_processor_mock_mode_on(self):
        processor = self.company._dfe_get_processor("nfe")
        self.assertIsInstance(processor, MockDfeClient)

    def test_get_processor_mock_mode_off_delegates(self):
        self.company.sudo().write({"dfe_mock_mode": False})
        try:
            with mock.patch(NFE_DFE_PROCESSOR) as patched_super:
                patched_super.return_value = "real_client"
                result = self.company._dfe_get_processor("nfe")
            self.assertEqual(result, "real_client")
        finally:
            self.company.sudo().write({"dfe_mock_mode": True})

    def test_get_processor_other_fiscal_type_delegates(self):
        """The pool only holds NF-e payloads, so other types reach super()."""
        with self.assertRaises(NotImplementedError):
            self.company._dfe_get_processor("cte")

    # ── consultar_distribuicao ──────────────────────────────────────────

    def test_empty_pool_returns_no_documents(self):
        resp = self.company._dfe_get_processor("nfe").consultar_distribuicao(
            ultimo_nsu="000000000000000"
        )
        self.assertEqual(resp.resposta.cStat, "137")
        self.assertFalse(resp.resposta.loteDistDFeInt.docZip)

    def test_pagination_returns_and_consumes_documents(self):
        record = self._create_nsu("000000000000001")
        resp = self.company._dfe_get_processor("nfe").consultar_distribuicao(
            ultimo_nsu="000000000000000"
        )
        self.assertEqual(resp.resposta.cStat, "138")
        self.assertEqual(resp.resposta.ultNSU, "000000000000001")
        doc_zips = resp.resposta.loteDistDFeInt.docZip
        self.assertEqual(len(doc_zips), 1)
        self.assertEqual(doc_zips[0].NSU, "000000000000001")
        self.assertEqual(doc_zips[0].schema, "resNFe_v1.00.xsd")
        self.assertEqual(
            gzip.decompress(doc_zips[0].value).decode("utf-8"), SAMPLE_RES_NFE
        )
        self.assertTrue(record.consumed)

    def test_pagination_skips_consumed_documents(self):
        self._create_nsu("000000000000001", consumed=True)
        resp = self.company._dfe_get_processor("nfe").consultar_distribuicao(
            ultimo_nsu="000000000000000"
        )
        self.assertEqual(resp.resposta.cStat, "137")

    def test_specific_search_by_access_key_does_not_consume(self):
        record = self._create_nsu("000000000000001")
        resp = self.company._dfe_get_processor("nfe").consultar_distribuicao(
            chave=ACCESS_KEY
        )
        self.assertEqual(resp.resposta.cStat, "138")
        self.assertEqual(len(resp.resposta.loteDistDFeInt.docZip), 1)
        self.assertFalse(record.consumed)

    def test_specific_search_by_nsu_does_not_consume(self):
        record = self._create_nsu("000000000000007")
        resp = self.company._dfe_get_processor("nfe").consultar_distribuicao(
            nsu_especifico="000000000000007"
        )
        self.assertEqual(resp.resposta.cStat, "138")
        self.assertFalse(record.consumed)

    # ── cooldown reset ──────────────────────────────────────────────────

    def test_reset_cooldown_clears_typed_field(self):
        self.company.sudo().write({"nfe_dfe_next_query": fields.Datetime.now()})
        self.company.with_company(self.company).action_reset_dfe_cooldown()
        self.assertFalse(self.company.nfe_dfe_next_query)

    # ── NFS-e: same pool, different fiscal_type ──────────────────────────

    def test_get_processor_mock_mode_on_nfse(self):
        processor = self.company._dfe_get_processor("nfse")
        self.assertIsInstance(processor, MockDfeClient)

    def test_nfse_pagination_returns_and_consumes_documents(self):
        record = self._create_nfse_nsu("000000000000001")
        resp = self.company._dfe_get_processor("nfse").consultar_distribuicao(
            ultimo_nsu="000000000000000"
        )
        self.assertEqual(resp.resposta.cStat, "138")
        doc_zips = resp.resposta.loteDistDFeInt.docZip
        self.assertEqual(len(doc_zips), 1)
        self.assertEqual(doc_zips[0].schema, "NFSe")
        self.assertEqual(
            gzip.decompress(doc_zips[0].value).decode("utf-8"), SAMPLE_NFSE
        )
        self.assertTrue(record.consumed)

    def test_nfse_specific_search_by_access_key(self):
        self._create_nfse_nsu("000000000000001")
        resp = self.company._dfe_get_processor("nfse").consultar_distribuicao(
            chave=NFSE_ACCESS_KEY
        )
        self.assertEqual(resp.resposta.cStat, "138")
        self.assertEqual(len(resp.resposta.loteDistDFeInt.docZip), 1)

    def test_nfe_and_nfse_pools_do_not_leak_into_each_other(self):
        """A query for one fiscal type must never return the other's
        mock documents, even though both share the same NSU pool
        model and the same company."""
        self._create_nsu("000000000000001")
        self._create_nfse_nsu("000000000000002")

        nfe_resp = self.company._dfe_get_processor("nfe").consultar_distribuicao(
            ultimo_nsu="000000000000000"
        )
        self.assertEqual(len(nfe_resp.resposta.loteDistDFeInt.docZip), 1)
        self.assertEqual(
            nfe_resp.resposta.loteDistDFeInt.docZip[0].schema, "resNFe_v1.00.xsd"
        )

        nfse_resp = self.company._dfe_get_processor("nfse").consultar_distribuicao(
            ultimo_nsu="000000000000000"
        )
        self.assertEqual(len(nfse_resp.resposta.loteDistDFeInt.docZip), 1)
        self.assertEqual(nfse_resp.resposta.loteDistDFeInt.docZip[0].schema, "NFSe")
