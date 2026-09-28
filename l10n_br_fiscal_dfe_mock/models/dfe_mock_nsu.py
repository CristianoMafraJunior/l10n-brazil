# Copyright 2026 Engenere (<https://engenere.one>)
# License AGPL-3 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class DfeMockNsu(models.Model):
    _name = "dfe.mock.nsu"
    _description = "DF-e Mock NSU"
    _order = "nsu"
    _rec_name = "nsu"

    nsu = fields.Char(string="NSU", size=15, required=True, index=True)
    fiscal_type = fields.Selection(
        selection=[
            ("nfe", "NF-e"),
            ("nfse", "NFS-e"),
        ],
        string="Fiscal Type",
        required=True,
    )
    schema_type = fields.Selection(
        selection=[
            ("resNFe", "resNFe"),
            ("procNFe", "procNFe"),
            ("resEvento", "resEvento"),
            ("procEventoNFe", "procEventoNFe"),
            ("resNfse", "resNfse"),
            ("procNfse", "procNfse"),
        ],
        string="Schema Type",
        required=True,
    )
    xml_content = fields.Text(required=True)
    access_key = fields.Char(size=44)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    consumed = fields.Boolean(default=False)

    _sql_constraints = [
        (
            "nsu_company_unique",
            "UNIQUE(nsu, company_id, fiscal_type)",
            "NSU must be unique per company and fiscal type.",
        ),
    ]

    def action_reset_consumed(self):
        self.write({"consumed": False})
