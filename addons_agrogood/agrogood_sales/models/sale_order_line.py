from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    agrogood_shortage_qty = fields.Float(
        string="Faltante",
        compute='_compute_agrogood_shortage_qty',
        store=True,
        digits='Product Unit of Measure',
        help="Cuanto falta para servir esta linea completa. Es lo que habria "
             "que reponer para poder entregar el pedido entero.",
    )

    @api.depends('product_uom_qty', 'free_qty_today', 'product_id', 'state',
                 'move_ids.state', 'move_ids.quantity', 'move_ids.product_uom_qty')
    def _compute_agrogood_shortage_qty(self):
        """Faltante, medido de forma distinta antes y despues de confirmar.

        Antes de confirmar no hay movimientos de stock, asi que la referencia
        es `free_qty_today`: lo libre hoy descontando lo comprometido en otros
        pedidos.

        Despues de confirmar hay que mirar los movimientos, no `free_qty_today`.
        El motivo es concreto: al confirmar, el pedido reserva stock y deja
        `free_qty_today` en negativo. Restarlo entonces cuenta el faltante dos
        veces, y un pedido de 20 kg sin stock aparecia como 40 kg de faltante.
        Lo que realmente falta es lo que el almacen no consiguio reservar.

        Los servicios no consumen stock, asi que nunca faltan.
        """
        for line in self:
            if line.display_type or not line.product_id or line.product_id.type == 'service':
                line.agrogood_shortage_qty = 0.0
                continue
            if line.state == 'cancel':
                line.agrogood_shortage_qty = 0.0
                continue

            pendientes = line.move_ids.filtered(lambda m: m.state not in ('cancel', 'done'))
            if pendientes:
                line.agrogood_shortage_qty = max(0.0, sum(
                    m.product_uom_qty - m.quantity for m in pendientes
                ))
            elif line.move_ids:
                # Todos los movimientos estan hechos o cancelados: nada falta.
                line.agrogood_shortage_qty = 0.0
            else:
                line.agrogood_shortage_qty = max(
                    0.0, line.product_uom_qty - (line.free_qty_today or 0.0)
                )
