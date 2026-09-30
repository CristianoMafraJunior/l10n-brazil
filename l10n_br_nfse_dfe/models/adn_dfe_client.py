# Copyright 2026 Cristiano Mafra Junior
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

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

PAGE_SIZE = 50
MAX_NSU_ATTEMPTS = 100
REQUEST_TIMEOUT = 30


@dataclass
class AdnDocZip:
    NSU: str
    schema_value: str
    schema: str
    value: bytes


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
        even a 404 ("no document") comes back with a JSON body, not an
        empty one, so we always try to parse it."""
        # TODO(adn): confirm exact NSU path formatting (zero-padded
        # 15-digit string, like SEFAZ, or a plain int — this uses a
        # plain int, which worked in our one live test).
        resp = session.get(f"{self.base_url}/DFe/{nsu}", timeout=REQUEST_TIMEOUT)
        if resp.status_code not in (200, 404):
            resp.raise_for_status()
        return resp.json()

    def _payload_to_doczips(self, payload):
        """Each ``LoteDFe`` entry has ``NSU``, ``ChaveAcesso``,
        ``TipoDocumento`` and ``ArquivoXml`` (gzip+base64, same as
        SEFAZ's docZip). ``Documento``/``Xml`` are kept as fallbacks
        only in case some document type/version uses different field
        names — not confirmed themselves."""
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

        if chave and not nsu_especifico:
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
        return several documents in ``LoteDFe`` — we collect across
        NSUs until we hit PAGE_SIZE documents found or
        MAX_NSU_ATTEMPTS NSUs checked, whichever comes first.

        IMPORTANT: ``last_checked_nsu`` advances on every NSU we check,
        found or not — earlier this only advanced on a *find*, which
        seemed safer (never skip a "not yet filled" NSU) but turned out
        to be wrong: ADN's numbering has real gaps, and stopping at the
        first miss permanently stalls the sync the first time one shows
        up. Always advancing means we walk straight through gaps up to
        MAX_NSU_ATTEMPTS per call, and never get stuck re-checking the
        same range forever.
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
                maxNSU=last_nsu_str,
                loteDistDFeInt=AdnLoteDistDFeInt(docZip=doc_zips),
            )
        )
