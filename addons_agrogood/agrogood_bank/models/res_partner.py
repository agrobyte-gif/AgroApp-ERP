from odoo import _, api, fields, models


class ResPartner(models.Model):
    """El saldo del cliente: lo que se le entrego menos lo que pago.

    Vive como campos del cliente y no en un modelo aparte, igual que las
    metricas de reactivacion: son atributos suyos, no entidades propias. Y se
    almacenan porque la lista de cobranza se ordena por saldo, y ordenar por un
    campo que se calcula al vuelo obliga a recorrer la cartera entera cada vez
    que alguien abre la pantalla.

    El saldo tiene dos partes: las ordenes entregadas y no pagadas, y el SALDO
    DE APERTURA -lo que el cliente ya debia el dia que se arranco Agroapp, de
    entregas que nunca pasaron por el sistema-. Sin la segunda, la cobranza
    arrancaria diciendo que nadie debe nada y habria que llevarla por fuera
    durante meses.
    """

    _inherit = 'res.partner'

    agrogood_credit_days = fields.Integer(
        string="Dias de plazo", default=0,
        help="Los dias que este cliente tiene para pagar desde la entrega. "
             "Cero es contado.",
    )

    # --- lo que ya debia antes de Agroapp ---
    #
    # Se guarda como un importe del cliente y NO como una orden de compra
    # inventada. Una orden falsa entraria en las ventas del dia, en el ticket
    # medio, en los productos mas vendidos y en los paneles, y cada informe
    # nuevo tendria que acordarse de excluirla. Un importe no se cuela en
    # ningun sitio.
    agrogood_opening_balance = fields.Monetary(
        string="Saldo de apertura", currency_field='currency_id',
        help="Lo que este cliente debia el dia que se arranco Agroapp, de "
             "entregas anteriores al sistema.",
    )
    agrogood_opening_date = fields.Date(
        string="Fecha de corte",
        help="Hasta cuando cubre el saldo de apertura. Desde esa fecha, lo que "
             "se debe son las ordenes de compra del sistema.",
    )
    agrogood_opening_allocation_ids = fields.One2many(
        comodel_name='agrogood.payment.allocation',
        inverse_name='opening_partner_id', string="Pagos al saldo de apertura",
    )
    agrogood_opening_due = fields.Monetary(
        string="Apertura pendiente", currency_field='currency_id',
        compute='_compute_agrogood_cobranza', store=True,
    )

    agrogood_balance = fields.Monetary(
        string="Saldo", compute='_compute_agrogood_cobranza', store=True,
        currency_field='currency_id',
        help="Lo entregado y no pagado, con IVA, mas lo que quede del saldo "
             "de apertura.",
    )
    agrogood_overdue_balance = fields.Monetary(
        string="Vencido", compute='_compute_agrogood_cobranza', store=True,
        currency_field='currency_id',
    )
    agrogood_open_order_count = fields.Integer(
        string="Ordenes por cobrar", compute='_compute_agrogood_cobranza',
        store=True,
    )
    agrogood_oldest_due_days = fields.Integer(
        string="Atraso mas antiguo", compute='_compute_agrogood_cobranza',
        store=True,
        help="Dias que lleva sin pagarse la deuda vencida mas antigua. Es el "
             "numero que decide a quien se llama primero.",
    )

    # Lo unico que se anota durante una llamada de cobranza. Vive en el cliente
    # y no en un modelo de promesas porque lo que hace falta consultar es la
    # ULTIMA -"a este ya lo llamamos y dijo el viernes"-, y el historial queda
    # en su conversacion, que es donde alguien va a buscarlo.
    agrogood_payment_promise_date = fields.Date(
        string="Prometio pagar el", copy=False,
        help="Lo que dijo el cliente la ultima vez que se le llamo.",
    )
    agrogood_payment_promise_note = fields.Char(
        string="Que dijo", copy=False,
    )

    @api.depends('sale_order_ids.agrogood_due_amount',
                 'sale_order_ids.agrogood_due_date',
                 'sale_order_ids.agrogood_collection_state',
                 'agrogood_opening_balance',
                 'agrogood_opening_date',
                 'agrogood_opening_allocation_ids.amount')
    def _compute_agrogood_cobranza(self):
        hoy = fields.Date.context_today(self)
        for socio in self:
            pagado_apertura = sum(
                socio.agrogood_opening_allocation_ids.mapped('amount'))
            apertura = max((socio.agrogood_opening_balance or 0.0)
                           - pagado_apertura, 0.0)
            socio.agrogood_opening_due = apertura

            abiertas = socio.sale_order_ids.filtered(
                lambda o: o.agrogood_collection_state in ('open', 'partial'))
            socio.agrogood_balance = (
                sum(abiertas.mapped('agrogood_due_amount')) + apertura)
            socio.agrogood_open_order_count = len(abiertas)

            vencidas = abiertas.filtered(
                lambda o: o.agrogood_due_date and o.agrogood_due_date < hoy)
            fechas = [o.agrogood_due_date for o in vencidas if o.agrogood_due_date]
            vencido = sum(vencidas.mapped('agrogood_due_amount'))

            # El saldo de apertura esta vencido por definicion: es deuda de
            # antes del corte, y si no lo estuviera no se habria cargado.
            if apertura and socio.agrogood_opening_date \
                    and socio.agrogood_opening_date <= hoy:
                vencido += apertura
                fechas.append(socio.agrogood_opening_date)

            socio.agrogood_overdue_balance = vencido
            socio.agrogood_oldest_due_days = (hoy - min(fechas)).days if fechas else 0

    def agrogood_registrar_promesa(self, fecha=None, nota=None):
        """Anota lo que dijo el cliente y lo deja en su conversacion.

        Se guarda el campo Y se publica en el chatter. El campo responde
        "cuando dijo que pagaba"; el chatter responde "cuantas veces lo ha
        dicho ya", que es la pregunta que decide si se le sigue llamando o se
        le corta el credito. Solo con el campo, cada promesa borra la anterior
        y el cliente que promete todos los viernes parece igual de fiable que
        el que cumple.
        """
        self.ensure_one()
        self.write({
            'agrogood_payment_promise_date': fecha or False,
            'agrogood_payment_promise_note': (nota or '').strip() or False,
        })
        partes = [_("Cobranza: se le llamo.")]
        if fecha:
            partes.append(_("Dijo que paga el %s.", fecha))
        if nota:
            partes.append(nota.strip())
        partes.append(_("Debia %(saldo)s en ese momento.",
                        saldo=self.agrogood_balance))
        self.message_post(body=" ".join(partes))
        return True

    def action_agrogood_cuenta_corriente(self):
        """Las ordenes por cobrar de este cliente."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Cuenta corriente de %s" % self.display_name,
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', 'child_of', self.commercial_partner_id.id),
                ('agrogood_collection_state', 'in', ('open', 'partial')),
            ],
            'context': {'create': False},
        }
