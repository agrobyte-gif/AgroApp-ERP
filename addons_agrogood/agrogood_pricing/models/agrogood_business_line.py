from odoo import _, fields, models


class AgrogoodBusinessLine(models.Model):
    """Extension de la linea comercial con su historial de precios.

    La linea comercial se define en `agrogood_base`, que deliberadamente no sabe
    nada de precios. Es este modulo el que le anade esa dimension.
    """

    _inherit = 'agrogood.business.line'

    price_version_ids = fields.One2many(
        comodel_name='agrogood.price.version',
        inverse_name='business_line_id',
        string="Versiones de precios",
    )
    price_version_count = fields.Integer(compute='_compute_price_version_count')

    def _compute_price_version_count(self):
        counts = dict(self.env['agrogood.price.version']._read_group(
            domain=[('business_line_id', 'in', self.ids)],
            groupby=['business_line_id'],
            aggregates=['__count'],
        ))
        for line in self:
            line.price_version_count = counts.get(line, 0)

    def action_view_price_versions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Precios de %s", self.name),
            'res_model': 'agrogood.price.version',
            'view_mode': 'list,form',
            'domain': [('business_line_id', '=', self.id)],
            'context': {
                'default_business_line_id': self.id,
                'default_pricelist_id': self.pricelist_id.id,
            },
        }
