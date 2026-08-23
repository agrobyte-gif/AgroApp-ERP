from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    agrogood_stop_id = fields.One2many(
        comodel_name='agrogood.route.stop', inverse_name='picking_id',
        string="Parada de ruta",
    )
    agrogood_route_id = fields.Many2one(
        comodel_name='agrogood.route', string="Ruta",
        compute='_compute_agrogood_route', store=True, index='btree_not_null',
    )

    @api.depends('agrogood_stop_id.route_id')
    def _compute_agrogood_route(self):
        for p in self:
            p.agrogood_route_id = p.agrogood_stop_id[:1].route_id
