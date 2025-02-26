from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.icms import ICMS_TAX_BENEFIT_TYPE


class IcmsBenefit(models.Model):
    _name = "l10n_br_fiscal.icms.benefit"

    code = fields.Char(size=8, required=True)

    name = fields.Char(required=True)

    description = fields.Text(required=True)

    benefit_type = fields.Selection(
        selection=ICMS_TAX_BENEFIT_TYPE,
        compute="_compute_benefit_type",
    )

    state = fields.Many2one(
        comodel_name="res.country.state",
        string="From State",
        domain=[("country_id.code", "=", "BR")],
        compute="_compute_state",
    )

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("code", "name", "state")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name} - {record.state.code}"

    @api.constrains("code")
    def _check_tax_benefit_code(self):
        for record in self:
            if record.code:
                if len(record.code) != 8:
                    raise ValidationError(_("Tax benefit code must be 8 characters!"))

    @api.depends("code")
    def _compute_benefit_type(self):
        for record in self:
            if record.code and len(record.code) >= 4:
                record.benefit_type = record.code[3]
            else:
                record.benefit_type = False

    @api.depends("code")
    def _compute_state(self):
        for record in self:
            record.state = (
                self.env["res.country.state"]
                .search(
                    [
                        ("country_id.code", "=", "BR"),
                        ("code", "=", record.code[:2].upper()),
                    ],
                    limit=1,
                )
                .id
                if record.code
                else False
            )
