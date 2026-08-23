from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends('state', 'agrogood_closed', 'invoice_status',
                 'picking_ids.state', 'order_line.agrogood_shortage_qty',
                 'picking_ids.agrogood_session_id.state')
    def _compute_agrogood_state(self):
        """Anade la sesion de preparacion a las dependencias del estado.

        Se redeclaran TODAS las dependencias, incluidas las de agrogood_sales:
        Odoo toma las del metodo que encuentra en el modelo, no las acumula.

        Sin esto el estado solo cambiaba cuando algo mas lo despertaba -por
        ejemplo al teclear una cantidad-, de modo que arrancar la preparacion
        no se reflejaba. Funcionaba a ratos, que es la peor forma de fallar.
        """
        return super()._compute_agrogood_state()

    def _agrogood_state_from_logistics(self):
        """Afina el estado operativo con lo que sabe la sesion de preparacion.

        `agrogood_sales` dejo este metodo devolviendo None a proposito, para
        que los modulos de operaciones lo completaran sin reescribir el
        calculo. Aqui se rellenan las dos etapas que solo conoce el Picker.
        """
        self.ensure_one()
        sesiones = self.picking_ids.filtered(
            lambda p: p.state not in ('cancel', 'done')).agrogood_session_id
        if not sesiones:
            return super()._agrogood_state_from_logistics()
        if any(s.state == 'in_progress' for s in sesiones):
            return 'picking'
        if all(s.state == 'done' for s in sesiones):
            return 'picked'
        return super()._agrogood_state_from_logistics()
