# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Tests for the ADN client.

These tests mock the HTTP transport (``requests.Session.get``) exactly
like the existing NF-e test suite mocks ``DefaultTransport.post`` —
they don't hit the real ADN, but the response shapes they mock are no
longer guesses: they were confirmed on 2026-09-22 against real
``GET /contribuintes/DFe/{NSU}`` calls to the homologação (produção
restrita) environment with a real A1 certificate, including one call
that returned a real NFS-e document (see the module docstring in
``adn_dfe_client.py`` for exactly what was confirmed).
"""

import base64
import gzip
from io import BytesIO
from unittest import mock

import requests

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_br_fiscal_dfe.tools import utils

from ..models.adn_dfe_client import (
    PRODUCTION_BASE_URL,
    SANDBOX_BASE_URL,
    AdnDfeClient,
)


def _gzip_base64(xml_str):
    buf = BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(xml_str.encode("utf-8"))
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _real_shaped_xml(access_key="3" * 50, body="<xLocEmi>MOCK</xLocEmi>"):
    """A minimal XML shaped like the real document confirmed live: the
    access key lives in the root <infNFSe Id="NFS<chave>"> attribute,
    not as a separate element."""
    return (
        '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
        f'<infNFSe Id="NFS{access_key}">{body}</infNFSe>'
        "</NFSe>"
    )


def _real_shaped_xml_with_metadata(
    access_key="3" * 50,
    emitter_name="EMPRESA TESTE LTDA",
    emitter_cnpj="21990799000180",
    document_number="2300000000054",
    amount="269.90",
    cstat="100",
    serie="45000",
    dh_emi="2023-01-11T00:00:00-03:00",
):
    """Same structure as the real document confirmed live on
    2026-09-22 (trimmed to just the fields the module extracts) —
    including a <prest><xNome> and <toma><xNome> with DIFFERENT names
    than <emit><xNome>, to make sure metadata extraction reads from
    the right element and not just "the first xNome it finds"."""
    return (
        '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
        f'<infNFSe Id="NFS{access_key}">'
        f"<nNFSe>{document_number}</nNFSe>"
        f"<cStat>{cstat}</cStat>"
        f"<emit><CNPJ>{emitter_cnpj}</CNPJ><xNome>{emitter_name}</xNome></emit>"
        f"<valores><vLiq>{amount}</vLiq></valores>"
        "<DPS>"
        "<infDPS>"
        f"<dhEmi>{dh_emi}</dhEmi>"
        f"<serie>{serie}</serie>"
        "<prest><xNome>NOT THE EMITTER</xNome></prest>"
        "<toma><xNome>NOT THE EMITTER EITHER</xNome></toma>"
        "</infDPS>"
        "</DPS>"
        "</infNFSe>"
        "</NFSe>"
    )


def _lote_item(nsu, xml_content="<NFSe>mock</NFSe>", access_key=None):
    """Real shape confirmed live for a LoteDFe entry."""
    return {
        "NSU": nsu,
        "ChaveAcesso": access_key or "",
        "TipoDocumento": "NFSE",
        "ArquivoXml": _gzip_base64(xml_content),
        "DataHoraGeracao": "2026-09-22T00:00:00.000",
    }


def _found_payload(items):
    """Real shape confirmed live — a successful lookup."""
    return {
        "StatusProcessamento": "DOCUMENTOS_LOCALIZADOS",
        "LoteDFe": items,
        "Alertas": [],
        "Erros": [],
        "TipoAmbiente": "HOMOLOGACAO",
    }


def _not_found_payload():
    """Real shape confirmed live — HTTP 404, "no document" response."""
    return {
        "StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO",
        "LoteDFe": [],
        "Alertas": [],
        "Erros": [
            {
                "Mensagem": {},
                "Codigo": "E2220",
                "Descricao": (
                    "Nenhum documento localizado - não existem documentos "
                    "fiscais para o Contribuinte a partir do NSU informado."
                ),
            }
        ],
        "TipoAmbiente": "HOMOLOGACAO",
    }


def _mock_response(status_code, json_data):
    resp = mock.Mock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    else:
        resp.raise_for_status.return_value = None
    return resp


def _found_response(nsu, xml_content="<NFSe>mock</NFSe>"):
    return _mock_response(200, _found_payload([_lote_item(nsu, xml_content)]))


def _not_found_response():
    return _mock_response(404, _not_found_payload())


class TestAdnDfeClient(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("l10n_br_base.empresa_lucro_presumido")

    # ── Environment selection ────────────────────────────────────────

    def test_sandbox_environment_uses_sandbox_url(self):
        self.company.nfse_environment = "2"
        client = AdnDfeClient(self.company)
        self.assertEqual(client.base_url, SANDBOX_BASE_URL)

    def test_production_environment_uses_production_url(self):
        self.company.nfse_environment = "1"
        client = AdnDfeClient(self.company)
        self.assertEqual(client.base_url, PRODUCTION_BASE_URL)

    # ── Certificate handling ─────────────────────────────────────────

    def test_missing_certificate_raises_user_error(self):
        self.company.nfse_environment = "2"
        self.company.certificate_nfe_id = False
        self.company.certificate_ecnpj_id = False
        client = AdnDfeClient(self.company)
        with self.assertRaises(UserError):
            client.consultar_distribuicao(
                cnpj_cpf="12345678000190", ultimo_nsu="000000000000000"
            )

    # ── Pagination mode (ultimo_nsu) ─────────────────────────────────

    @mock.patch.object(requests.Session, "get")
    def test_pagination_finds_one_document_then_stops(self, mock_get):
        self.company.nfse_environment = "2"
        mock_get.side_effect = [
            _found_response(1, "<NFSe>doc-1</NFSe>"),
            _not_found_response(),
        ]

        client = AdnDfeClient(self.company)
        result = client.consultar_distribuicao(
            cnpj_cpf="12345678000190", ultimo_nsu="000000000000000"
        )

        self.assertEqual(result.resposta.cStat, "138")
        self.assertEqual(len(result.resposta.loteDistDFeInt.docZip), 1)
        self.assertEqual(result.resposta.ultNSU, utils.format_nsu("1"))
        self.assertEqual(result.resposta.maxNSU, result.resposta.ultNSU)
        self.assertEqual(mock_get.call_count, 2)

        doc_zip = result.resposta.loteDistDFeInt.docZip[0]
        with gzip.GzipFile(fileobj=BytesIO(doc_zip.value)) as gz:
            self.assertIn(b"doc-1", gz.read())

    @mock.patch.object(requests.Session, "get")
    def test_pagination_no_documents_returns_137(self, mock_get):
        self.company.nfse_environment = "2"
        mock_get.return_value = _not_found_response()

        client = AdnDfeClient(self.company)
        result = client.consultar_distribuicao(
            cnpj_cpf="12345678000190", ultimo_nsu="000000000000005"
        )

        self.assertEqual(result.resposta.cStat, "137")
        self.assertFalse(result.resposta.loteDistDFeInt.docZip)
        mock_get.assert_called_once()

    @mock.patch.object(requests.Session, "get")
    def test_pagination_stops_at_page_size(self, mock_get):
        self.company.nfse_environment = "2"
        mock_get.side_effect = lambda url, **kw: _found_response(1)

        client = AdnDfeClient(self.company)
        result = client.consultar_distribuicao(
            cnpj_cpf="12345678000190", ultimo_nsu="000000000000000"
        )

        self.assertEqual(len(result.resposta.loteDistDFeInt.docZip), 50)
        self.assertEqual(mock_get.call_count, 50)

    @mock.patch.object(requests.Session, "get")
    def test_pagination_batch_per_call(self, mock_get):
        """A single call's LoteDFe can hold more than one document —
        confirmed structurally live, even though we never saw a
        non-empty one to exercise this with real data."""
        self.company.nfse_environment = "2"
        mock_get.side_effect = [
            _mock_response(
                200,
                _found_payload(
                    [_lote_item(1, "<NFSe>a</NFSe>"), _lote_item(2, "<NFSe>b</NFSe>")]
                ),
            ),
            _not_found_response(),
        ]

        client = AdnDfeClient(self.company)
        result = client.consultar_distribuicao(
            cnpj_cpf="12345678000190", ultimo_nsu="000000000000000"
        )

        self.assertEqual(len(result.resposta.loteDistDFeInt.docZip), 2)
        self.assertEqual(mock_get.call_count, 2)

    # ── Specific search mode (nsu_especifico) ────────────────────────

    @mock.patch.object(requests.Session, "get")
    def test_specific_nsu_found(self, mock_get):
        self.company.nfse_environment = "2"
        mock_get.return_value = _found_response(42)

        client = AdnDfeClient(self.company)
        result = client.consultar_distribuicao(
            cnpj_cpf="12345678000190", nsu_especifico="42"
        )

        self.assertEqual(result.resposta.cStat, "138")
        self.assertEqual(len(result.resposta.loteDistDFeInt.docZip), 1)

    @mock.patch.object(requests.Session, "get")
    def test_specific_nsu_not_found(self, mock_get):
        self.company.nfse_environment = "2"
        mock_get.return_value = _not_found_response()

        client = AdnDfeClient(self.company)
        result = client.consultar_distribuicao(
            cnpj_cpf="12345678000190", nsu_especifico="42"
        )

        self.assertEqual(result.resposta.cStat, "137")

    def test_specific_search_by_access_key_not_implemented(self):
        self.company.nfse_environment = "2"
        client = AdnDfeClient(self.company)
        with self.assertRaises(UserError):
            client.consultar_distribuicao(cnpj_cpf="12345678000190", chave="3" * 44)

    def test_invalid_nsu_raises_user_error(self):
        self.company.nfse_environment = "2"
        client = AdnDfeClient(self.company)
        with self.assertRaises(UserError):
            client.consultar_distribuicao(
                cnpj_cpf="12345678000190", nsu_especifico="not-a-number"
            )

    # ── cnpjConsulta must NOT be sent by default ─────────────────────

    @mock.patch.object(requests.Session, "get")
    def test_cnpj_cpf_is_not_forwarded_as_query_param(self, mock_get):
        """Confirmed live: sending cnpjConsulta when it doesn't share
        the certificate's CNPJ root fails with HTTP 400 / E2243. Since
        we don't support matriz/filial lookups yet, we must never send
        it — the server defaults to the certificate's own CNPJ."""
        self.company.nfse_environment = "2"
        mock_get.return_value = _not_found_response()

        client = AdnDfeClient(self.company)
        client.consultar_distribuicao(cnpj_cpf="12345678000190", nsu_especifico="1")

        _args, called_kwargs = mock_get.call_args
        self.assertNotIn("params", called_kwargs)

    # ── Malformed response ────────────────────────────────────────────

    @mock.patch.object(requests.Session, "get")
    def test_unexpected_lote_item_shape_raises_user_error(self, mock_get):
        mock_get.return_value = _mock_response(
            200, _found_payload([{"NSU": "1", "unexpected": "shape"}])
        )

        client = AdnDfeClient(self.company)
        with self.assertRaises(UserError):
            client.consultar_distribuicao(cnpj_cpf="12345678000190", nsu_especifico="1")


class TestResCompanyNfseDfe(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("l10n_br_base.empresa_lucro_presumido")
        cls.company.nfse_environment = "2"

    def test_dfe_get_processor_returns_adn_client_for_nfse(self):
        processor = self.company._dfe_get_processor("nfse")
        self.assertIsInstance(processor, AdnDfeClient)

    def test_dfe_get_processor_delegates_for_other_fiscal_types(self):
        with self.assertRaises(NotImplementedError):
            self.company._dfe_get_processor("nfe")

    @mock.patch.object(requests.Session, "get")
    def test_search_documents_groups_under_document_by_access_key(self, mock_get):
        """Full round trip through the generic engine: ``_dfe_create_
        from_NFSe`` should find the access key in the payload and group
        the downloaded document under a ``l10n_br_fiscal_dfe.document``
        (not just leave a bare, ungrouped ``.dfe`` record)."""
        access_key = "3" * 50
        xml = _real_shaped_xml(access_key)
        mock_get.side_effect = [
            _found_response(1, xml),
            _not_found_response(),
        ]

        self.company.nfse_dfe_search_documents()

        self.assertEqual(self.company.nfse_last_nsu, utils.format_nsu("1"))
        dfe_record = self.env["l10n_br_fiscal_dfe.dfe"].search(
            [
                ("company_id", "=", self.company.id),
                ("fiscal_type", "=", "nfse"),
            ],
            limit=1,
        )
        self.assertTrue(dfe_record)
        self.assertEqual(dfe_record.schema_type, "NFSe")
        self.assertTrue(dfe_record.attachment_id)
        # Regression check: the dfe record's own access_key/document_type_dfe
        # must be set too, not just the parent document's — otherwise the
        # XML attachment filename ends up literally named "NFSe_False.xml"
        # (caught against a real production document on 2026-09-22).
        self.assertEqual(dfe_record.access_key, access_key)
        self.assertEqual(dfe_record.document_type_dfe, "complete")
        self.assertIn(access_key, dfe_record.attachment_id.name)

        document = self.env["l10n_br_fiscal_dfe.document"].search(
            [("access_key", "=", access_key)]
        )
        self.assertTrue(document, "document should be grouped by the found access key")
        self.assertIn(dfe_record, document.dfe_ids)

    @mock.patch.object(requests.Session, "get")
    def test_search_documents_extracts_display_metadata(self, mock_get):
        """The document's Valor/Emitente columns shouldn't stay blank —
        extract them from the same fields confirmed on a real document
        (caught 2026-09-22: everything showed 0,00/empty because this
        wasn't implemented yet)."""
        access_key = "4" * 50
        xml = _real_shaped_xml_with_metadata(access_key=access_key)
        mock_get.side_effect = [
            _found_response(1, xml),
            _not_found_response(),
        ]

        self.company.nfse_dfe_search_documents()

        document = self.env["l10n_br_fiscal_dfe.document"].search(
            [("access_key", "=", access_key)]
        )
        self.assertTrue(document)
        self.assertEqual(document.emitter, "EMPRESA TESTE LTDA")
        self.assertEqual(document.vat, "21.990.799/0001-80")
        self.assertEqual(document.document_number, "2300000000054")
        self.assertAlmostEqual(document.document_amount, 269.90)
        self.assertEqual(document.document_state, "100")
        self.assertEqual(document.serie, "45000")
        self.assertEqual(document.document_emission_date.year, 2023)
        self.assertEqual(document.document_emission_date.month, 1)
        self.assertEqual(document.document_emission_date.day, 11)

    @mock.patch.object(requests.Session, "get")
    def test_search_documents_without_access_key_stays_ungrouped(self, mock_get):
        """When the payload has no recognizable access key, the record
        is still created (degrades gracefully), just not grouped."""
        mock_get.side_effect = [
            _found_response(1, "<NFSe>no key here</NFSe>"),
            _not_found_response(),
        ]

        self.company.nfse_dfe_search_documents()

        dfe_record = self.env["l10n_br_fiscal_dfe.dfe"].search(
            [
                ("company_id", "=", self.company.id),
                ("fiscal_type", "=", "nfse"),
            ],
            limit=1,
        )
        self.assertTrue(dfe_record)
        self.assertFalse(dfe_record.dfe_document_id)

    @mock.patch.object(requests.Session, "get")
    def test_search_documents_no_docs_does_not_crash(self, mock_get):
        mock_get.return_value = _not_found_response()
        self.company.nfse_dfe_search_documents()
        self.assertEqual(self.company.nfse_dfe_last_status_code, "137")

    def test_action_banner_search_all_nfse(self):
        """action_banner_search_all_nfse delegates to current company."""
        self.company.nfse_dfe_next_query = False
        with mock.patch.object(
            type(self.company),
            "_dfe_document_distribution",
            return_value=None,
        ):
            ResCompany = self.env["res.company"].with_company(self.company)
            result = ResCompany.action_banner_search_all_nfse()
        self.assertEqual(result["tag"], "reload")

    def test_action_banner_specific_search_nfse(self):
        """action_banner_specific_search_nfse returns wizard action."""
        ResCompany = self.env["res.company"].with_company(self.company)
        result = ResCompany.action_banner_specific_search_nfse()
        self.assertEqual(result["res_model"], "dfe.specific.search.wizard")
        self.assertEqual(result["target"], "new")
        self.assertEqual(result["context"]["default_fiscal_type"], "nfse")
