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
        required=True,
        default="nfe",
    )
    schema_type = fields.Selection(
        selection=[
            ("resNFe", "resNFe"),
            ("procNFe", "procNFe"),
            ("resEvento", "resEvento"),
            ("procEventoNFe", "procEventoNFe"),
            ("NFSe", "NFSe"),
        ],
        required=True,
    )
    xml_content = fields.Text(required=True)
    # NF-e access keys are 44 digits, NFS-e Nacional's are 50 — no fixed
    # size so the same field fits both.
    access_key = fields.Char()
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    consumed = fields.Boolean(default=False)

    _sql_constraints = [
        (
            "nsu_company_unique",
            "UNIQUE(nsu, company_id)",
            "NSU must be unique per company.",
        ),
    ]

    def action_reset_consumed(self):
        self.write({"consumed": False})
