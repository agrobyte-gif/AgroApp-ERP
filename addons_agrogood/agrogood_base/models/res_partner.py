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

    agrogood_billing_blocked = fields.Boolean(
        string="No facturable",
        compute='_compute_agrogood_billing',
        store=True,
        help="Al cliente le falta algun dato obligatorio para emitirle factura. "
             "Puede recibir pedidos y despachos igualmente.",
    )
    agrogood_billing_blocker = fields.Char(
        string="Motivo",
        compute='_compute_agrogood_billing',
        store=True,
        help="Que dato falta exactamente.",
    )

    @api.depends('vat', 'agrogood_business_line_id')
    def _compute_agrogood_billing(self):
        """Marca los clientes a los que aun no se puede facturar, y por que.

        El bloqueo en si NO se implementa aqui: `l10n_cl` ya lo aplica de forma
        nativa al validar el documento. Lo que falta, y es lo que aporta esto,
        es poder encontrarlos y completarlos antes de que el problema aparezca
        con el pedido ya entregado.

        Se limita a los contactos con linea comercial para no marcar
        proveedores, empleados ni contactos internos.
        """
        for partner in self:
            motivos = partner._agrogood_billing_blockers()                 if partner.agrogood_business_line_id else []
            partner.agrogood_billing_blocked = bool(motivos)
            partner.agrogood_billing_blocker = " / ".join(motivos)

    def _agrogood_billing_blockers(self):
        """Devuelve los motivos por los que no se puede facturar a este cliente.

        Punto de extension deliberado: cada localizacion exige datos distintos.
        `agrogood_sales` anade aqui el tipo de contribuyente, que en Chile es
        tan obligatorio como el RUT.
        """
        self.ensure_one()
        return [] if self.vat else ["Falta el RUT"]

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
