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

    @api.depends('agrogood_stop_id.route_id', 'agrogood_stop_id.state')
    def _compute_agrogood_route(self):
        """La ruta VIVA de este albaran, si tiene alguna.

        Las paradas reprogramadas no cuentan: son el intento de otro dia que no
        salio. Si contaran, el albaran seguiria pareciendo asignado a la ruta
        de ayer y no volveria a aparecer en la lista de Logistica, que es justo
        lo que hay que arreglar al reprogramar una entrega.
        """
        for p in self:
            vivas = p.agrogood_stop_id.filtered(
                lambda s: s.state != 'rescheduled')
            p.agrogood_route_id = vivas[:1].route_id
