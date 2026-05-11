# Copyright (C) 2016  Daniel Sadamo - KMEE Informática
# Copyright 2025 Akretion - Renato Lima <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import fields, models


class HrContractLaborRegime(models.Model):
    _name = "hr.contract.labor.regime"
    _inherit = "l10n_br_hr_contract.data.abstract"
    _description = "Type of employment contract"

    name = fields.Char(string="Labor regime")

    short_name = fields.Char()

    code = fields.Char(size=1)

    def _compute_display_name(self):
        for data in self:
            name = data.name
            if data.short_name:
                name = f"{data.short_name} - {data.name}"
            data.display_name = name
