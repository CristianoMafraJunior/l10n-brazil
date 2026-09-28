# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3 or later (http://www.gnu.org/licenses/agpl)

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from odoo import models

# ── Mock dataclasses imitating nfelib MDE response ──────────────────────


@dataclass
class _MockInfEvento:
    cStat: str = "135"
    xMotivo: str = "Evento registrado e vinculado a NF-e"
    nProt: str = ""
    dhRegEvento: str = ""


@dataclass
class _MockRetEvento:
    infEvento: _MockInfEvento = field(default_factory=_MockInfEvento)


@dataclass
class _MockResposta:
    retEvento: list = field(default_factory=list)


@dataclass
class _MockRetorno:
    status_code: int = 200
    _content: bytes = b"<mock>MDE mock response</mock>"


@dataclass
class _MockMDeResult:
    retorno: _MockRetorno = field(default_factory=_MockRetorno)
    resposta: _MockResposta = field(default_factory=_MockResposta)


def _build_mde_result():
    """Build a successful mock MDE result."""
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-03:00")
    nprot = f"MOCK{random.randint(100000000000, 999999999999)}"
    inf = _MockInfEvento(
        cStat="135",
        xMotivo="Evento registrado e vinculado a NF-e",
        nProt=nprot,
        dhRegEvento=now_iso,
    )
    return _MockMDeResult(
        retorno=_MockRetorno(),
        resposta=_MockResposta(retEvento=[_MockRetEvento(infEvento=inf)]),
    )


# ── Generic MDE Processor for all fiscal document types ─────────────────


class _MockMDeProcessor:
    """Emulates the MDeAdapter for all four manifestation operations.

    This processor is generic and works for NF-e, NFS-e, CT-e, MDF-e, etc.,
    depending on the event type and fiscal document type configured.
    """

    def ciencia_da_operacao(self, chave, cnpj_dest):
        return _build_mde_result()

    def confirmacao_da_operacao(self, chave, cnpj_dest):
        return _build_mde_result()

    def desconhecimento_da_operacao(self, chave, cnpj_dest):
        return _build_mde_result()

    def operacao_nao_realizada(self, chave, cnpj_dest):
        return _build_mde_result()


# ── Odoo model override ────────────────────────────────────────────────


class NfeRecipientManifestationEvent(models.Model):
    _inherit = "l10n_br_nfe.md_event"

    def _get_processor(self):
        if self.company_id.dfe_mock_mode:
            _logger.info("MDE mock: using _MockMDeProcessor for %s", self.access_key)
            return _MockMDeProcessor()
        return super()._get_processor()

    def action_confirm(self):
        result = super().action_confirm()
        for record in self.filtered(
            lambda r: r.company_id.dfe_mock_mode and r.event_type == "ciente"
        ):
            record._mock_generate_proc()
        return result

    def _mock_generate_proc(self):
        """After ciência, auto-generate the appropriate manifestation XML
        in the mock pool based on the event type and fiscal document type."""
        MockNsu = self.env["dfe.mock.nsu"].sudo()
        access_key = self.access_key
        fiscal_type = self.fiscal_type or "nfe"

        # Determine the schema_type based on fiscal_type and event_type
        schema_map = {
            ("nfe", "ciente"): "procNFe",
            ("nfse", "ciente"): "procNfse",
            ("cte", "ciente"): "procCte",
            ("mdfe", "ciente"): "procMdf",
        }
        default_schema = "procNFe"  # fallback

        schema_type = schema_map.get((fiscal_type, "ciente"), default_schema)

        existing = MockNsu.search(
            [
                ("company_id", "=", self.company_id.id),
                ("access_key", "=", access_key),
                ("schema_type", "=", schema_type),
            ],
            limit=1,
        )
        if existing:
            _logger.info(
                "MDE mock: %s already exists for key %s (NSU %s)",
                schema_type,
                access_key,
                existing.nsu,
            )
            return

        # Find a matching res document in the mock pool
        res_schema = "resNFe" if fiscal_type == "nfe" else "resNfse"
        res_nfe = MockNsu.search(
            [
                ("company_id", "=", self.company_id.id),
                ("access_key", "=", access_key),
                ("schema_type", "=", res_schema),
            ],
            limit=1,
        )
        if not res_nfe:
            _logger.warning(
                "MDE mock: no res document found for key %s, cannot generate %s",
                access_key,
                schema_type,
            )
            return

        partner_data, amount, emission_dt = self._mock_parse_res(
            res_nfe.xml_content, fiscal_type
        )

        wizard = self.env["dfe.mock.generate.wizard"].new(
            {"company_id": self.company_id.id}
        )
        proc_xml = wizard._build_proc_xml(
            access_key, partner_data, amount, emission_dt, fiscal_type
        )

        next_nsu = wizard._next_nsu(self.company_id)
        nsu_str = str(next_nsu).zfill(15)

        MockNsu.create(
            {
                "nsu": nsu_str,
                "schema_type": schema_type,
                "xml_content": proc_xml,
                "access_key": access_key,
                "company_id": self.company_id.id,
                "consumed": False,
                "fiscal_type": fiscal_type,
            }
        )
        _logger.info(
            "MDE mock: created %s NSU %s for key %s", schema_type, nsu_str, access_key
        )

    def _mock_parse_res(self, xml_content, fiscal_type):
        """Extract partner data, amount, and emission date from resXML.

        Supports NF-e, NFS-e, CT-e, and MDF-e XML formats.
        """

        _logger = logging.getLogger(__name__)

        # Try to detect the XML namespace/format
        if "<resNFe" in xml_content or "<NFe" in xml_content:
            ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
            return self._parse_nfe_xml(xml_content, ns, fiscal_type)
        elif "<resNfse" in xml_content or "<NFSe" in xml_content:
            # NFS-e format parsing
            ns = {"nfse": "http://www.sped.fazenda.gov.br/nfse"}
            return self._parse_nfse_xml(xml_content, ns, fiscal_type)
        elif "<resCte" in xml_content or "<Cte" in xml_content:
            # CT-e format parsing
            ns = {"cte": "http://www.portalfiscal.inf.br/cte"}
            return self._parse_cte_xml(xml_content, ns, fiscal_type)
        elif "<resMdf" in xml_content or "<Mdf" in xml_content:
            # MDF-e format parsing
            ns = {"mdf": "http://www.portalfiscal.inf.br/mdfe"}
            return self._parse_mdf_xml(xml_content, ns, fiscal_type)
        else:
            _logger.warning("MDE mock: unknown XML format, using defaults")
            # Default generic parsing
            cnpj = ""
            name = "Emitente Mock"
            ie = "ISENTO"
            amount = 1000.00
            # Try to extract dhEmi
            dh_match = re.search(r"<dhEmi>([^<]+)</dhEmi>", xml_content)
            if dh_match:
                try:
                    emission_dt = datetime.fromisoformat(
                        re.sub(r"[+-]\d{2}:\d{2}$", "", dh_match.group(1))
                    )
                except Exception:
                    emission_dt = datetime.now()
            else:
                emission_dt = datetime.now()
            return {"cnpj": cnpj, "name": name, "ie": ie}, amount, emission_dt

    def _parse_nfe_xml(self, xml_content, ns, fiscal_type):
        """Extract partner data, amount, and emission date from NF-e resNFe XML."""
        root = etree.fromstring(xml_content.encode("utf-8"))

        def _text(tag, default=""):
            el = root.find(f"nfe:{tag}", ns)
            if el is None:
                el = root.find(tag)
            return el.text if el is not None and el.text else default

        cnpj = _text("CNPJ")
        name = _text("xNome", "Emitente Mock")
        ie = _text("IE", "ISENTO")
        vnf = float(_text("vNF", "1000.00"))

        dh_emi_str = _text("dhEmi", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        emission_dt = datetime.fromisoformat(
            re.sub(r"[+-]\d{2}:\d{2}$", "", dh_emi_str)
        )

        cnpj_digits = re.sub(r"[^0-9]", "", cnpj)
        uf_code = cnpj_digits[:2] if len(cnpj_digits) >= 2 else "35"
        if self.access_key and len(self.access_key) >= 2:
            uf_code = self.access_key[:2]

        partner_data = {
            "cnpj": cnpj_digits,
            "name": name,
            "uf_code": uf_code,
            "ie": ie,
        }
        return partner_data, vnf, emission_dt

    def _parse_nfse_xml(self, xml_content, ns, fiscal_type):
        """Extract partner data from NFS-e resEvento XML."""
        try:
            root = etree.fromstring(xml_content.encode("utf-8"))
            # NFS-e has different structure; try namespace-agnostic search
            # Try to find CNPJ and xNome using local names
            cnpj_el = root.find(".//CNPJ") if root is not None else None
            nome_el = root.find(".//xNome") if root is not None else None

            cnpj = cnpj_el.text if cnpj_el is not None and cnpj_el.text else ""
            name = (
                nome_el.text
                if nome_el is not None and nome_el.text
                else "Emitente Mock"
            )
            ie = "ISENTO"

            # Try to find vLiq (total amount)
            vliq_el = root.find(".//vLiq") if root is not None else None
            amount = (
                float(vliq_el.text) if vliq_el is not None and vliq_el.text else 1000.00
            )

            # Try to find dhEmi
            dh_emi_el = root.find(".//dhEmi") if root is not None else None
            dh_emi_str = (
                dh_emi_el.text
                if dh_emi_el is not None and dh_emi_el.text
                else datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            )
            emission_dt = datetime.fromisoformat(
                re.sub(r"[+-]\d{2}:\d{2}$", "", dh_emi_str)
            )

            partner_data = {"cnpj": cnpj, "name": name, "ie": ie}
            return partner_data, amount, emission_dt
        except Exception:
            _logger.exception("MDE mock: error parsing NFS-e XML")
            return {
                "cnpj": "",
                "name": "Emitente Mock",
                "ie": "ISENTO",
            }, 1000.00, datetime.now()

    def _parse_cte_xml(self, xml_content, ns, fiscal_type):
        """Placeholder for CT-e XML parsing."""
        _logger.warning(
            "MDE mock: CT-e XML parsing not fully implemented, using defaults"
        )
        return {
            "cnpj": "",
            "name": "Emitente Mock",
            "ie": "ISENTO",
        }, 1000.00, datetime.now()

    def _parse_mdf_xml(self, xml_content, ns, fiscal_type):
        """Placeholder for MDF-e XML parsing."""
        _logger.warning(
            "MDE mock: MDF-e XML parsing not fully implemented, using defaults"
        )
        return {
            "cnpj": "",
            "name": "Emitente Mock",
            "ie": "ISENTO",
        }, 1000.00, datetime.now()
