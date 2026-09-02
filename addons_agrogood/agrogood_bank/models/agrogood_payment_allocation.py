from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AgrogoodPaymentAllocation(models.Model):
    """Que parte de que abono paga que orden de compra.

    Hace falta una tabla aparte porque la relacion es de muchos a muchos y con
    importe: un cliente junta cuatro entregas en una transferencia, y otro paga
    una entrega grande en dos veces. Guardar el pago en la orden -o la orden en
    el pago- solo cubre el caso facil, y en cobranza el caso facil no es el que
    da problemas.

    Se imputa el importe exacto, no la orden entera. Asi una transferencia que
    cubre tres entregas y media queda registrada como lo que es, y la media
    sigue apareciendo como deuda en vez de desaparecer redondeada.
    """

    _name = 'agrogood.payment.allocation'
    _description = "Pago imputado a una orden de compra"
    _order = 'movement_id, order_id'

    movement_id = fields.Many2one(
        comodel_name='agrogood.bank.movement', string="Abono",
        required=True, ondelete='cascade', index=True,
    )
    order_id = fields.Many2one(
        comodel_name='sale.order', string="Orden de compra",
        required=True, ondelete='cascade', index=True,
    )
    amount = fields.Monetary(string="Importe imputado", required=True)
    currency_id = fields.Many2one(related='movement_id.currency_id')
    date = fields.Date(related='movement_id.date', store=True, index=True)
    partner_id = fields.Many2one(related='order_id.partner_id', store=True,
                                 index=True)

    @api.constrains('amount', 'movement_id', 'order_id')
    def _check_importes(self):
        """Ni el abono ni la orden pueden quedar imputados por encima.

        Es la comprobacion que impide que la cuenta corriente mienta. Sin ella,
        un dedazo al imputar deja una orden como pagada de mas y el saldo del
        cliente en negativo, y eso no se descubre hasta que alguien reclama.
        """
        for a in self:
            if a.amount <= 0:
                raise ValidationError(_("El importe imputado tiene que ser "
                                        "mayor que cero."))
            imputado = sum(a.movement_id.allocation_ids.mapped('amount'))
            if a.currency_id.compare_amounts(imputado, a.movement_id.amount) > 0:
                raise ValidationError(_(
                    "No se puede repartir mas de lo que trae el abono. El "
                    "abono es de %(abono)s y se estan imputando %(imputado)s.",
                    abono=a.movement_id.amount, imputado=imputado))
            en_la_orden = sum(a.order_id.agrogood_allocation_ids.mapped('amount'))
            if a.currency_id.compare_amounts(
                    en_la_orden, a.order_id.agrogood_charge_amount) > 0:
                raise ValidationError(_(
                    "La orden %(orden)s quedaria pagada de mas: se puede "
                    "cobrar %(cobrable)s y se estan imputando %(imputado)s.",
                    orden=a.order_id.name,
                    cobrable=a.order_id.agrogood_charge_amount,
                    imputado=en_la_orden))
