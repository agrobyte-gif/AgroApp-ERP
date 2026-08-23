from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Al confirmar un pedido se refrescan las metricas de ese cliente.

        El proceso nocturno mantiene el conjunto al dia, pero esperar a manana
        para saber que un cliente acaba de comprar dejaria su seguimiento
        abierto y alguien lo llamaria para pedirle lo que ya pidio.
        """
        res = super().action_confirm()
        socios = self.partner_id.commercial_partner_id.filtered(
            'agrogood_business_line_id')
        if socios:
            socios._agrogood_recompute_metrics()
        # El seguimiento pendiente se cierra solo: el objetivo ya se cumplio.
        seguimientos = self.env['agrogood.followup'].search([
            ('partner_id', 'in', socios.ids),
            ('state', 'in', ('pending', 'contacted', 'rescheduled')),
        ])
        for s in seguimientos:
            s.write({'state': 'order_created',
                     'sale_order_id': s.sale_order_id.id or self[:1].id})
        return res
