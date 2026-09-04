from odoo import models


class StockPicking(models.Model):
    """El puente entre recibir en bodega y cerrar la solicitud de compra.

    Cuando se valida una recepcion de una orden de compra, las solicitudes que
    dieron origen a esa orden se enteran y se cierran solas. Es el cruce que
    pedia el tablero: "el ingreso de compras se cruza con el control de
    bodega". Antes, recibir y cerrar la solicitud eran dos actos separados, y
    el segundo se olvidaba.
    """

    _inherit = 'stock.picking'

    def _action_done(self):
        # Se deja que Odoo termine de validar -y de calcular qty_received en la
        # orden- antes de mirar nada: recien despues lo recibido es un hecho.
        res = super()._action_done()
        recepciones = self.filtered(
            lambda p: p.picking_type_code == 'incoming' and p.purchase_id)
        if recepciones:
            solicitudes = self.env['agrogood.purchase.request'].sudo().search([
                ('purchase_order_id', 'in', recepciones.purchase_id.ids),
                ('state', '=', 'purchased'),
            ])
            solicitudes._cerrar_por_recepcion()
        return res
