from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    agrogood_business_line_id = fields.Many2one(
        comodel_name='agrogood.business.line',
        string="Linea comercial",
        index=True,
        tracking=True,
        help="Segmento comercial del cliente. Determina la tarifa y las condiciones "
             "que se proponen al crear un pedido.",
    )

    @api.onchange('agrogood_business_line_id')
    def _onchange_agrogood_business_line_id(self):
        """Propone la tarifa de la linea comercial, sin imponerla.

        Se hace por onchange y no por compute para que Ventas pueda apartarse del
        valor por defecto en un cliente concreto sin que el sistema lo revierta.

        La condicion de pago no se trata aqui: `account.payment.term` pertenece al
        modulo `account` y este modulo es la base de la que depende todo lo demas,
        incluida la PWA. Anadir `account` a sus dependencias obligaria a Pickers y
        Conductores a arrastrar contabilidad. La condicion de pago por linea
        comercial se anade desde `agrogood_sales`, que si depende de `account`.
        """
        line = self.agrogood_business_line_id
        if line.pricelist_id:
            self.property_product_pricelist = line.pricelist_id
