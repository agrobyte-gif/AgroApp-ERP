from odoo import fields, models


class AgrogoodBusinessLine(models.Model):
    """Condiciones comerciales de la linea que dependen de contabilidad.

    La condicion de pago no cabe en `agrogood_base`: `account.payment.term`
    pertenece a `account`, y agrogood_base es la base de la que cuelga todo,
    incluida la PWA de bodega. Se anade desde aqui, que si depende de account
    a traves de sale_stock.
    """

    _inherit = 'agrogood.business.line'

    payment_term_id = fields.Many2one(
        comodel_name='account.payment.term',
        string="Condicion de pago por defecto",
        help="Se propone al asignar esta linea comercial a un cliente. No se "
             "aplica de forma retroactiva a los clientes existentes.",
    )
