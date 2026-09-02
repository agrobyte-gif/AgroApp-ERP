from odoo import api, fields, models

COBRANZA = [
    ('nothing', "Nada que cobrar todavia"),
    ('open', "Por cobrar"),
    ('partial', "Pagada en parte"),
    ('paid', "Pagada"),
]


class SaleOrder(models.Model):
    """La orden de compra como documento de cobro.

    Agrogood emite sus facturas en el portal del SII, no en Odoo: aqui no hay
    ni una `account.move` de venta. Por eso la cobranza se lleva sobre la orden
    de compra, que es el documento que si existe en el sistema y el que el
    cliente reconoce -es como Agrogood llama a su pedido de venta-.

    **Se debe lo entregado, no lo pedido.** Es la misma regla de ADR-003 que
    aplica la facturacion: si se pidieron 20 kg y se entregaron 19,4, se cobran
    19,4. Cobrar lo pedido convertiria cada diferencia de peso en una discusion
    con el cliente, y en este rubro la diferencia de peso es la norma.
    """

    _inherit = 'sale.order'

    agrogood_allocation_ids = fields.One2many(
        comodel_name='agrogood.payment.allocation', inverse_name='order_id',
        string="Pagos imputados",
    )

    agrogood_charge_amount = fields.Monetary(
        string="Cobrable", compute='_compute_agrogood_cobranza', store=True,
        help="Lo entregado de esta orden, con IVA. Es lo que se le puede "
             "cobrar al cliente hoy.",
    )
    agrogood_paid_amount = fields.Monetary(
        string="Pagado", compute='_compute_agrogood_cobranza', store=True,
    )
    agrogood_due_amount = fields.Monetary(
        string="Debe", compute='_compute_agrogood_cobranza', store=True,
    )
    agrogood_collection_state = fields.Selection(
        selection=COBRANZA, string="Cobranza",
        compute='_compute_agrogood_cobranza', store=True, index=True,
    )

    # El plazo se copia del cliente al tomar el pedido y se queda AQUI. Si se
    # leyera siempre de la ficha, ampliarle el plazo a un cliente moroso
    # descontaria de golpe todas sus entregas vencidas y desapareceria de la
    # lista de cobranza sin haber pagado nada. Vale el plazo que se pacto ese
    # dia, no el de hoy.
    agrogood_credit_days = fields.Integer(
        string="Dias de plazo", compute='_compute_agrogood_credit_days',
        store=True, readonly=False,
    )
    agrogood_due_date = fields.Date(
        string="Vence", compute='_compute_agrogood_due_date', store=True,
        help="La fecha del pedido mas los dias de plazo pactados. Sin plazo, "
             "vence el mismo dia: es venta al contado.",
    )
    agrogood_overdue_days = fields.Integer(
        string="Dias de atraso", compute='_compute_agrogood_overdue_days',
    )

    # El documento tributario se emite fuera de Odoo. Aqui solo se anota su
    # numero, porque es como el cliente se refiere a la deuda cuando se le
    # llama: "te pagué la 1234". Sin el numero, cobranza y cliente hablan de
    # documentos distintos.
    agrogood_sii_folio = fields.Char(
        string="Folio SII", copy=False, index=True,
        help="Numero del documento emitido en el portal del SII.",
    )
    agrogood_sii_date = fields.Date(string="Fecha del documento", copy=False)

    @api.depends('state', 'order_line.qty_delivered', 'order_line.price_total',
                 'order_line.product_uom_qty', 'agrogood_allocation_ids.amount')
    def _compute_agrogood_cobranza(self):
        for order in self:
            cobrable = 0.0
            if order.state in ('sale', 'done'):
                for linea in order.order_line:
                    pedido = linea.product_uom_qty or 0.0
                    if pedido <= 0 or linea.display_type:
                        continue
                    # Proporcional sobre el total con impuestos: mantiene el
                    # IVA y cualquier descuento de la linea sin recalcularlos.
                    cobrable += linea.price_total * (linea.qty_delivered / pedido)
            pagado = sum(order.agrogood_allocation_ids.mapped('amount'))
            debe = cobrable - pagado
            order.agrogood_charge_amount = cobrable
            order.agrogood_paid_amount = pagado
            order.agrogood_due_amount = debe
            if order.currency_id.is_zero(cobrable):
                order.agrogood_collection_state = 'nothing'
            elif order.currency_id.is_zero(debe) or debe < 0:
                order.agrogood_collection_state = 'paid'
            elif pagado > 0:
                order.agrogood_collection_state = 'partial'
            else:
                order.agrogood_collection_state = 'open'

    @api.depends('partner_id')
    def _compute_agrogood_credit_days(self):
        """Se copia al elegir el cliente y no se vuelve a tocar solo.

        Depende de `partner_id` y no de `partner_id.agrogood_credit_days`: al
        cambiar de cliente en un pedido en borrador se trae su plazo, pero
        cambiar el plazo en la ficha no reescribe las ordenes ya tomadas.
        """
        for order in self:
            order.agrogood_credit_days = order.partner_id.agrogood_credit_days or 0

    @api.depends('date_order', 'agrogood_credit_days')
    def _compute_agrogood_due_date(self):
        for order in self:
            if not order.date_order:
                order.agrogood_due_date = False
                continue
            order.agrogood_due_date = fields.Date.add(
                order.date_order.date(), days=order.agrogood_credit_days or 0)

    def _compute_agrogood_overdue_days(self):
        hoy = fields.Date.context_today(self)
        for order in self:
            vence = order.agrogood_due_date
            atrasado = (order.agrogood_due_amount > 0 and vence and vence < hoy)
            order.agrogood_overdue_days = (hoy - vence).days if atrasado else 0
