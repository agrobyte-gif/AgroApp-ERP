from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends('state', 'agrogood_closed', 'invoice_status',
                 'picking_ids.state', 'order_line.agrogood_shortage_qty',
                 'picking_ids.agrogood_session_id.state',
                 'picking_ids.agrogood_stop_id.state',
                 'picking_ids.agrogood_stop_id.route_id.state')
    def _compute_agrogood_state(self):
        """Anade la ruta a las dependencias del estado operativo.

        Como en los modulos anteriores, se redeclaran TODAS: Odoo toma las del
        metodo que encuentra en el modelo, no las acumula.
        """
        return super()._compute_agrogood_state()

    def _agrogood_state_from_logistics(self):
        """Completa las dos etapas que solo conoce el reparto.

        Se consulta antes que la preparacion porque un pedido que ya va en el
        camion no esta 'preparado': esta en ruta.
        """
        self.ensure_one()
        paradas = self.picking_ids.filtered(
            lambda p: p.state != 'cancel').agrogood_stop_id
        if paradas:
            if any(s.route_id.state == 'in_progress'
                   and s.state in ('on_the_way', 'arrived') for s in paradas):
                return 'in_route'
            if any(s.route_id.state in ('draft', 'planned') for s in paradas):
                return 'to_dispatch'
        return super()._agrogood_state_from_logistics()
