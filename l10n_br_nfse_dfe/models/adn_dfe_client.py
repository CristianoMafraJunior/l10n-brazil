# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Client for the ADN (Ambiente de Dados Nacional) DF-e API.

Confirmed against a real ``GET /contribuintes/DFe/{NSU}`` call to the
homologação (produção restrita) environment on 2026-09-22, using a
real A1 certificate:

  - The URL is ``https://adn.producaorestrita.nfse.gov.br/contribuintes
    /DFe/{NSU}`` (sandbox) / ``https://adn.nfse.gov.br/contribuintes
    /DFe/{NSU}`` (production). mTLS with the company's A1 certificate
    works exactly as expected.
  - HTTP 404 means "no document found", with a JSON body shaped like::

        {
          "StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO",
          "LoteDFe": [],
          "Alertas": [],
          "Erros": [{"Mensagem": {}, "Codigo": "E2220",
                      "Descricao": "Nenhum documento localizado..."}],
          "TipoAmbiente": "HOMOLOGACAO",
          "VersaoAplicativo": "1.0.0.0",
          "DataHoraProcessamento": "..."
        }

  - Documents (when found) travel in the ``LoteDFe`` list — so a
    single call may return more than one document, more like SEFAZ's
    NF-e distribution than we originally assumed from the manual's
    wording. Confirmed against a real document on 2026-09-22, a
    ``LoteDFe`` entry looks like::

        {
          "NSU": 2,
          "ChaveAcesso": "<50-digit access key>",
          "TipoDocumento": "NFSE",
          "ArquivoXml": "<gzip+base64 XML, same as SEFAZ's docZip>",
          "DataHoraGeracao": "2023-01-11T10:36:34.393"
        }

  - The decoded XML root is ``<NFSe xmlns="http://www.sped.fazenda
    .gov.br/nfse">`` — there is NO dedicated "chave de acesso" element.
    The key only appears embedded in the root ``<infNFSe Id="NFS
    <chave>">`` attribute (same "3-letter prefix + key" convention
    NF-e uses: ``NFe<chave>``) and as free text inside ``<xOutInf>``.
    See ``_nfse_find_access_key`` in ``res_company.py``.
  - A ``cnpjConsulta`` query param does exist, but sending it when it
    doesn't share the certificate's CNPJ *root* fails with HTTP 400 and
    ``Erros[0].Codigo == "E2243"``. It's only for matriz/filial lookups
    (querying a different CNPJ under the same root) — the generic
    engine always passes a ``cnpj_cpf``, so sending it unconditionally
    broke the common case. We stopped sending it by default; see
    ``consultar_distribuicao``.
  - ADN's NSU numbering has real gaps: confirmed live (2026-09-23) on a
    production company with 101 real documents spanning NSU 2-110,
    NSU 53-60 (8 consecutive values) never resolved to a document for
    this CNPJ — presumably other tenants/event types consume slots in
    what's likely a shared national counter. The original design
    stopped walking at the first empty NSU, which is wrong for this
    API: it permanently stalled the sync the first time a gap showed
    up (``nfse_last_nsu`` stayed frozen even after 100+ more documents
    existed past the gap). See ``_consultar_paginado``.

Everything still marked ``TODO(adn)`` below has NOT been confirmed.
"""

import base64
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field

import requests
from erpbrasil.assinatura.certificado import Certificado

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.l10n_br_fiscal_dfe.constants.dfe import CSTAT_NO_DOCS, CSTAT_SUCCESS

PRODUCTION_BASE_URL = "https://adn.nfse.gov.br/contribuintes"
SANDBOX_BASE_URL = "https://adn.producaorestrita.nfse.gov.br/contribuintes"

STATUS_NO_DOCS = "NENHUM_DOCUMENTO_LOCALIZADO"

# TODO(adn): confirmed that a single call CAN return a list (LoteDFe),
# but not confirmed whether ADN caps it, or at what size. We still cap
# our own NSU walk at this many DOCUMENTS FOUND per call, to keep each
# cron tick bounded regardless.
PAGE_SIZE = 50

# Confirmed live (2026-09-23): ADN's NSU numbering has real gaps (8
# consecutive missing values seen on a real company). This bounds how
# many NSUs we'll walk *past* without finding anything before giving
# up for this call — i.e. the gap tolerance — separately from PAGE_SIZE
# (which caps documents *found*, not NSUs *checked*). Picked somewhat
# arbitrarily at ~12x the largest gap we've actually observed; not
# validated against a larger real gap.
MAX_NSU_ATTEMPTS = 100

REQUEST_TIMEOUT = 30


@dataclass
class AdnDocZip:
    NSU: str
    schema_value: str
    schema: str
    value: bytes  # gzipped XML, base64-decoded


@dataclass
class AdnLoteDistDFeInt:
    docZip: list = field(default_factory=list)


@dataclass
class AdnResposta:
    cStat: str
    xMotivo: str
    ultNSU: str
    maxNSU: str
    loteDistDFeInt: AdnLoteDistDFeInt = field(default_factory=AdnLoteDistDFeInt)


@dataclass
class AdnRetorno:
    content: bytes = b""
    _content: bytes = b""


@dataclass
class AdnWrappedResponse:
    resposta: AdnResposta
    envio_xml: bytes = b""
    retorno: AdnRetorno = field(default_factory=AdnRetorno)


@contextmanager
def _mtls_session(certificate):
    """Build a ``requests`` session authenticated with the company's A1
    certificate, cleaning up the temporary PEM files on exit.

    We build the PEM files ourselves (rather than using
    ``erpbrasil.assinatura.certificado.ArquivoCertificado``) because
    that helper writes cert/key content to swapped file paths — its own
    docstring example doesn't match what it actually does. Sticking to
    ``Certificado.cert_chave()`` directly avoids relying on that.
    """
    if not certificate or not certificate.file or not certificate.password:
        raise UserError(_("No A1 certificate configured for this company."))

    try:
        certificado = Certificado(arquivo=certificate.file, senha=certificate.password)
    except Exception as exc:
        raise UserError(
            _("Could not load the company's A1 certificate: %(error)s", error=exc)
        ) from exc

    cert_pem, key_pem = certificado.cert_chave()

    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = os.path.join(tmpdir, "cert.pem")
        key_path = os.path.join(tmpdir, "key.pem")
        with open(cert_path, "w", encoding="utf-8") as fh:
            fh.write(cert_pem)
        with open(key_path, "w", encoding="utf-8") as fh:
            fh.write(key_pem)

        session = requests.Session()
        session.cert = (cert_path, key_path)
        try:
            yield session
        finally:
            session.close()


class AdnDfeClient:
    """Stand-in for the ADN REST client, mirroring the interface the
    generic DF-e engine expects from ``_dfe_get_processor``'s return
    value: a ``consultar_distribuicao(**kwargs)`` method."""

    def __init__(self, company):
        self.company = company
        self.base_url = (
            PRODUCTION_BASE_URL if company.nfse_environment == "1" else SANDBOX_BASE_URL
        )

    def _get_dfe(self, session, nsu):
        """GET /DFe/{NSU}. Returns the parsed JSON body in every case —
        confirmed live that even a 404 ("no document") comes back with
        a JSON body, not an empty one, so we always try to parse it."""
        # TODO(adn): confirm exact NSU path formatting (zero-padded
        # 15-digit string, like SEFAZ, or a plain int — this uses a
        # plain int, which worked in our one live test).
        resp = session.get(f"{self.base_url}/DFe/{nsu}", timeout=REQUEST_TIMEOUT)
        if resp.status_code not in (200, 404):
            resp.raise_for_status()
        return resp.json()

    def _payload_to_doczips(self, payload):
        """Confirmed live (2026-09-22): each ``LoteDFe`` entry has
        ``NSU``, ``ChaveAcesso``, ``TipoDocumento`` and ``ArquivoXml``
        (gzip+base64, same as SEFAZ's docZip). ``Documento``/``Xml``
        are kept as fallbacks only in case some document type/version
        uses different field names — not confirmed themselves."""
        doc_zips = []
        for item in payload.get("LoteDFe") or []:
            nsu = item.get("NSU") or item.get("Nsu")
            xml_b64 = (
                item.get("ArquivoXml")
                or item.get("Documento")
                or item.get("Xml")
                or item.get("documento")
            )
            if not xml_b64:
                raise UserError(
                    _(
                        "Unexpected ADN LoteDFe entry shape: could not find "
                        "the XML payload field. This adapter needs to be "
                        "updated against the real item contract: %(item)s",
                        item=item,
                    )
                )
            doc_zips.append(
                AdnDocZip(
                    NSU=str(nsu).zfill(15) if nsu else "",
                    schema_value="NFSe",
                    schema="NFSe",
                    value=base64.b64decode(xml_b64),
                )
            )
        return doc_zips

    def consultar_distribuicao(self, **kwargs):
        nsu_especifico = kwargs.get("nsu_especifico")
        chave = kwargs.get("chave")
        ultimo_nsu = kwargs.get("ultimo_nsu") or "000000000000000"

        # NOTE: the generic engine always passes cnpj_cpf, but sending
        # it as the ADN "cnpjConsulta" param when it doesn't share the
        # certificate's CNPJ root fails with HTTP 400 / E2243 (verified
        # live). It's only meant for matriz/filial lookups, which this
        # module doesn't support yet, so we never send it — the server
        # defaults to the certificate's own CNPJ, which is what we want.

        if chave and not nsu_especifico:
            # TODO(adn): the distribution manual we read doesn't expose
            # a "give me the document for this access key" endpoint —
            # only by-NSU and events-by-access-key. Specific search by
            # access key isn't implemented yet for NFS-e.
            raise UserError(
                _(
                    "Specific search by access key is not implemented yet "
                    "for NFS-e (ADN only supports document lookup by NSU "
                    "so far)."
                )
            )

        with _mtls_session(self.company.certificate) as session:
            if nsu_especifico:
                return self._consultar_nsu_especifico(session, nsu_especifico)
            return self._consultar_paginado(session, ultimo_nsu)

    @staticmethod
    def _to_int_nsu(nsu):
        try:
            return int(nsu)
        except (TypeError, ValueError) as exc:
            raise UserError(_("Invalid NSU: %(nsu)s", nsu=nsu)) from exc

    def _consultar_nsu_especifico(self, session, nsu_especifico):
        nsu_int = self._to_int_nsu(nsu_especifico)
        nsu_str = str(nsu_int).zfill(15)
        payload = self._get_dfe(session, nsu_int)

        if payload.get("StatusProcessamento") == STATUS_NO_DOCS:
            return AdnWrappedResponse(
                resposta=AdnResposta(
                    cStat=CSTAT_NO_DOCS,
                    xMotivo=_("No document found for the informed NSU."),
                    ultNSU=nsu_str,
                    maxNSU=nsu_str,
                )
            )

        doc_zips = self._payload_to_doczips(payload)
        if not doc_zips:
            return AdnWrappedResponse(
                resposta=AdnResposta(
                    cStat=CSTAT_NO_DOCS,
                    xMotivo=_("No document found for the informed NSU."),
                    ultNSU=nsu_str,
                    maxNSU=nsu_str,
                )
            )
        return AdnWrappedResponse(
            resposta=AdnResposta(
                cStat=CSTAT_SUCCESS,
                xMotivo=_("Document found."),
                ultNSU=nsu_str,
                maxNSU=nsu_str,
                loteDistDFeInt=AdnLoteDistDFeInt(docZip=doc_zips),
            )
        )

    def _consultar_paginado(self, session, ultimo_nsu):
        """Pagination mode: walk NSU one by one. Each call may itself
        return several documents in ``LoteDFe`` (confirmed structurally,
        though we've only ever seen more than one entry) — we collect
        across NSUs until we hit PAGE_SIZE documents found or
        MAX_NSU_ATTEMPTS NSUs checked, whichever comes first.

        IMPORTANT: ``last_checked_nsu`` advances on every NSU we check,
        found or not — earlier this only advanced on a *find*, which
        seemed safer (never skip a "not yet filled" NSU) but turned out
        to be wrong: ADN's numbering has real gaps (confirmed live,
        2026-09-23), and stopping at the first miss permanently stalled
        the sync the first time one showed up. Always advancing means
        we walk straight through gaps up to MAX_NSU_ATTEMPTS per call,
        and never get stuck re-checking the same range forever.
        """
        doc_zips = []
        current_nsu = self._to_int_nsu(ultimo_nsu)
        last_checked_nsu = current_nsu
        attempts = 0
        while len(doc_zips) < PAGE_SIZE and attempts < MAX_NSU_ATTEMPTS:
            current_nsu += 1
            attempts += 1
            payload = self._get_dfe(session, current_nsu)
            last_checked_nsu = current_nsu

            if payload.get("StatusProcessamento") == STATUS_NO_DOCS:
                continue

            found = self._payload_to_doczips(payload)
            doc_zips.extend(found)

        last_nsu_str = str(last_checked_nsu).zfill(15)
        if not doc_zips:
            return AdnWrappedResponse(
                resposta=AdnResposta(
                    cStat=CSTAT_NO_DOCS,
                    xMotivo=_("No new documents found for the CNPJ."),
                    ultNSU=last_nsu_str,
                    maxNSU=last_nsu_str,
                )
            )

        return AdnWrappedResponse(
            resposta=AdnResposta(
                cStat=CSTAT_SUCCESS,
                xMotivo=_("Document(s) found."),
                ultNSU=last_nsu_str,
                # TODO(adn): ADN doesn't obviously expose a "highest NSU
                # available" figure the way SEFAZ's maxNSU does. Setting
                # maxNSU == ultNSU makes the generic engine stop after
                # this batch and simply retry on the next scheduled
                # run, which is safe but may be more conservative than
                # necessary.
                maxNSU=last_nsu_str,
                loteDistDFeInt=AdnLoteDistDFeInt(docZip=doc_zips),
            )
        )
