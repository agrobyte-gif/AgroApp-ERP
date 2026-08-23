from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    agrogood_request_ids = fields.One2many(
        comodel_name='agrogood.purchase.request',
        inverse_name='sale_order_id',
        string="Solicitudes de compra",
    )
    agrogood_request_count = fields.Integer(compute='_compute_agrogood_request_count')

    def _compute_agrogood_request_count(self):
        counts = dict(self.env['agrogood.purchase.request']._read_group(
            domain=[('sale_order_id', 'in', self.ids)],
            groupby=['sale_order_id'],
            aggregates=['__count'],
        ))
        for order in self:
            order.agrogood_request_count = counts.get(order, 0)

    def action_agrogood_request_replenishment(self):
        """Crea una solicitud de compra por cada linea con faltante.

        Es el puente entre el pedido y la pizarra de Compras: lo que Ventas
        detecta como faltante deja de vivir en la cabeza de alguien y pasa a
        ser trabajo con estado y responsable.

        No se duplica: una linea que ya genero una solicitud abierta se salta.
        Volver a pulsar el boton despues de que entre stock parcial crea solo
        lo que siga faltando.
        """
        Solicitud = self.env['agrogood.purchase.request']
        creadas = Solicitud
        for order in self:
            if order.state not in ('sale', 'done'):
                raise UserError(_(
                    "Confirma el pedido antes de pedir reposicion: hasta entonces "
                    "el faltante puede cambiar."
                ))
            for line in order.order_line:
                if line.agrogood_shortage_qty <= 0:
                    continue
                abierta = Solicitud.search([
                    ('sale_order_line_id', '=', line.id),
                    ('state', 'not in', ('cancelled', 'rejected', 'not_found')),
                ], limit=1)
                if abierta:
                    continue
                creadas |= Solicitud.create({
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom.id,
                    'qty_requested': line.agrogood_shortage_qty,
                    'partner_id': order.partner_id.commercial_partner_id.id,
                    'sale_order_id': order.id,
                    'sale_order_line_id': line.id,
                    'date_needed': (order.commitment_date or order.date_order).date(),
                    'reason': 'shortage',
                    # Un pedido ya confirmado que no se puede servir es urgente
                    # por definicion: el cliente lo espera.
                    'priority': '1',
                    'note': _(
                        "Faltan %(falta)s %(unidad)s de %(pedido)s "
                        "(pedidos %(total)s).",
                        falta=line.agrogood_shortage_qty,
                        unidad=line.product_uom.name,
                        pedido=order.name,
                        total=line.product_uom_qty,
                    ),
                })
            if creadas:
                order.message_post(body=_(
                    "Se generaron %(n)s solicitudes de compra: %(refs)s",
                    n=len(creadas), refs=", ".join(creadas.mapped('name')),
                ))

        if not creadas:
            raise UserError(_(
                "No hay nada que reponer: ninguna linea tiene faltante sin "
                "solicitud abierta."
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Solicitudes generadas"),
            'res_model': 'agrogood.purchase.request',
            'view_mode': 'list,form',
            'domain': [('id', 'in', creadas.ids)],
        }

    def action_agrogood_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Solicitudes de %s", self.name),
            'res_model': 'agrogood.purchase.request',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
        }
