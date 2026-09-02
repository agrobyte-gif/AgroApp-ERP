from odoo import _, api, fields, models
from odoo.exceptions import UserError

ESTADOS = [
    ('identified', "Se sabe quien pago"),
    ('doubtful', "Hay que mirarlo"),
    ('unknown', "Sin identificar"),
    ('discarded', "No es un cobro"),
]

# Como se dedujo el cliente. Se guarda porque en una pantalla de dinero hay que
# poder responder "y esto por que dice que es de este cliente".
MOTIVOS = {
    'rut_aprendido': "Por un RUT ya enlazado a este cliente",
    'rut_ficha': "Por el RUT de la ficha del cliente",
    'alias_aprendido': "Por el nombre corto ya enlazado",
    'compartida': "Ese pagador lo usan varios clientes",
    'discrepan': "El RUT dice un cliente y el nombre dice otro",
    'nada': "No se reconocio al pagador",
    'manual': "Lo enlazo una persona",
}


class AgrogoodBankMovement(models.Model):
    """Un abono de la cartola, con el cliente que hay detras.

    Es una tabla de trabajo, no contabilidad. Aqui no se asienta ningun pago:
    el modulo responde "este abono es de este cliente, que debe estas
    facturas", y asentarlo sigue siendo una decision de una persona con la
    factura delante. Esa frontera es deliberada -dar por cobrada la factura
    equivocada se descubre semanas despues, cuando se reclama una deuda que ya
    estaba pagada-.

    El trabajo que ahorra no es leer la cartola: es buscar. De los abonos de un
    mes real, la mayoria trae el RUT del pagador y se resuelven sin que nadie
    haga nada. Lo que queda es una lista corta.
    """

    _name = 'agrogood.bank.movement'
    _description = "Abono de la cartola"
    _order = 'date desc, amount desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)

    # --- lo que dice el banco, tal cual ---
    bank = fields.Selection(
        selection=[('scotiabank', "Scotiabank"), ('santander', "Santander")],
        string="Banco", required=True, index=True, readonly=True,
    )
    sheet = fields.Char(string="Hoja", readonly=True)
    date = fields.Date(string="Fecha", required=True, index=True, readonly=True)
    amount = fields.Monetary(string="Monto", required=True, readonly=True)
    currency_id = fields.Many2one(
        comodel_name='res.currency', readonly=True,
        default=lambda self: self.env.company.currency_id,
    )
    payer_rut = fields.Char(string="RUT del pagador", index=True, readonly=True)
    payer_alias = fields.Char(string="Nombre en el banco", index=True, readonly=True)
    payer_name = fields.Char(string="Titular", readonly=True)
    description = fields.Char(string="Descripcion", readonly=True)
    source_account = fields.Char(string="Cuenta de origen", readonly=True)

    # Lo que impide que volver a subir el mismo archivo duplique los abonos.
    unique_key = fields.Char(required=True, index=True, readonly=True)

    # --- lo que deduce el sistema ---
    partner_id = fields.Many2one(
        comodel_name='res.partner', string="Cliente", index=True,
        domain="[('customer_rank', '>', 0)]",
    )
    state = fields.Selection(
        selection=ESTADOS, string="Situacion", default='unknown',
        required=True, index=True,
    )
    match_reason = fields.Char(string="Por que", readonly=True)

    # --- a que ordenes de compra se imputa ---
    allocation_ids = fields.One2many(
        comodel_name='agrogood.payment.allocation', inverse_name='movement_id',
        string="Imputado a",
    )
    amount_applied = fields.Monetary(
        string="Imputado", compute='_compute_imputado', store=True,
    )
    amount_unapplied = fields.Monetary(
        string="Sin imputar", compute='_compute_imputado', store=True,
        help="Lo que queda de este abono por asignar a alguna orden.",
    )

    # --- lo que hace falta para decidir ---
    partner_due = fields.Monetary(
        related='partner_id.agrogood_balance', string="Debe en total",
        help="Lo que este cliente tiene entregado y sin pagar ahora mismo.",
    )
    order_match_id = fields.Many2one(
        comodel_name='sale.order', string="Orden que calza",
        compute='_compute_deuda',
        help="Una orden suya cuyo saldo coincide exactamente con lo que queda "
             "de este abono. Cuando aparece, no hay nada que buscar.",
    )

    imported_on = fields.Datetime(string="Cargado el", readonly=True,
                                  default=fields.Datetime.now)
    company_id = fields.Many2one(
        comodel_name='res.company', default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('abono_unico', 'unique(unique_key, company_id)',
         "Ese abono ya estaba cargado."),
    ]

    @api.depends('bank', 'date', 'amount')
    def _compute_name(self):
        for m in self:
            m.name = "%s %s %s" % (
                dict(self._fields['bank'].selection).get(m.bank, ''),
                m.date or '', "{:,.0f}".format(m.amount or 0).replace(",", "."))

    @api.depends('allocation_ids.amount', 'amount')
    def _compute_imputado(self):
        for m in self:
            m.amount_applied = sum(m.allocation_ids.mapped('amount'))
            m.amount_unapplied = m.amount - m.amount_applied

    def _ordenes_abiertas(self):
        """Las ordenes de compra del cliente que quedan por cobrar, la mas
        antigua primero. Cobrar por antiguedad no es una preferencia: es lo que
        evita que una deuda vieja se quede atras mientras se van pagando las
        nuevas."""
        self.ensure_one()
        if not self.partner_id:
            return self.env['sale.order'].browse()
        return self.env['sale.order'].search([
            ('partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('agrogood_collection_state', 'in', ('open', 'partial')),
        ], order='date_order asc')

    @api.depends('partner_id', 'amount_unapplied')
    def _compute_deuda(self):
        """Si alguna orden calza justo con lo que queda del abono.

        Se busca coincidencia EXACTA y no aproximada. Un abono que se PARECE a
        una orden no dice nada util: en distribucion hay decenas de entregas de
        importe parecido la misma semana, y la que se parece casi nunca es la
        que se pago.
        """
        for m in self:
            m.order_match_id = False
            if not m.partner_id or m.currency_id.is_zero(m.amount_unapplied):
                continue
            calza = m._ordenes_abiertas().filtered(
                lambda o: m.currency_id.is_zero(
                    o.agrogood_due_amount - m.amount_unapplied))
            m.order_match_id = calza[:1]

    # ------------------------------------------------------------------
    # cruce

    def _cruzar(self):
        """Vuelve a deducir el cliente de cada abono. Devuelve cuantos cambiaron.

        Es idempotente y se puede repetir cuantas veces haga falta, que es todo
        el punto: se enlazan diez abonos desconocidos a mano, se vuelve a
        cruzar, y los cientos que venian del mismo pagador quedan resueltos de
        una vez. Sin ese boton, cada uno habria que tocarlo por separado.

        Lo enlazado a mano y lo descartado no se toca. Una persona ya decidio
        ahi, y volver a cruzar no es motivo para deshacerlo.
        """
        Identidad = self.env['agrogood.payer']
        cambiados = 0
        for m in self:
            if m.state in ('discarded',) or m.match_reason == MOTIVOS['manual']:
                continue
            socio, motivo = Identidad.resolver(rut=m.payer_rut, alias=m.payer_alias)
            estado = 'identified' if socio else (
                'doubtful' if motivo in ('discrepan', 'compartida') else 'unknown')
            if m.partner_id != socio or m.state != estado:
                cambiados += 1
            # Sin aprender. El cruce automatico escribe el mismo campo que una
            # persona, de modo que sin esta marca se ensenaria a si mismo: el
            # primer abono que acierta por el RUT de la ficha crea la
            # identidad, y a partir de ahi todo lo demas cruza "por un RUT ya
            # enlazado" sin que nadie lo haya enlazado nunca. Un error inicial
            # se convertiria en regla y se repetiria solo.
            m.with_context(agrogood_sin_aprender=True).write({
                'partner_id': socio.id if socio else False,
                'state': estado,
                'match_reason': MOTIVOS.get(motivo, motivo),
            })
        return cambiados

    def action_cruzar(self):
        """Boton: volver a cruzar lo que sigue sin identificar."""
        pendientes = self.filtered(lambda m: m.state in ('unknown', 'doubtful'))
        objetivo = pendientes or self
        cambiados = objetivo._cruzar()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success' if cambiados else 'warning',
                'message': _("%(n)s abonos quedaron resueltos.", n=cambiados)
                if cambiados else _(
                    "Ninguno cambio. Hace falta enlazar alguno a mano primero: "
                    "cada uno que se enlaza resuelve los demas del mismo pagador."),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_descartar(self):
        """No es un cobro de cliente: traspaso entre cuentas, prestamo, factoring."""
        self.write({'state': 'discarded', 'partner_id': False,
                    'match_reason': _("Descartado a mano")})

    def write(self, vals):
        """Enlazar a mano ensena; el resto no.

        Es la unica puerta por la que se aprende. Un cruce automatico no ensena
        nunca: aprender de lo que uno mismo dedujo convierte un error en una
        regla y a partir de ahi se repite solo.
        """
        aprender = 'partner_id' in vals and vals.get('partner_id') \
            and not self.env.context.get('agrogood_sin_aprender')
        anteriores = {m.id: m.partner_id for m in self} if aprender else {}
        res = super().write(vals)
        if not aprender:
            return res
        Identidad = self.env['agrogood.payer']
        for m in self:
            if anteriores.get(m.id) == m.partner_id:
                continue
            Identidad.aprender(m.partner_id, rut=m.payer_rut,
                               alias=m.payer_alias, bank=m.bank)
            m.with_context(agrogood_sin_aprender=True).write({
                'state': 'identified', 'match_reason': MOTIVOS['manual'],
            })
        return res

    def action_ver_ordenes(self):
        """Las ordenes por cobrar de este cliente."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Primero hay que decir de quien es este abono."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Por cobrar a %s", self.partner_id.display_name),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self._ordenes_abiertas().ids)],
            'context': {'create': False},
        }

    def action_imputar(self):
        """Reparte el abono entre las ordenes pendientes, la mas antigua primero.

        Es una propuesta, no un asiento: deja las lineas de imputacion a la
        vista y se pueden borrar una a una si el cliente pagaba otra cosa. Lo
        habitual es que acierte -en distribucion se paga por antiguedad-, y lo
        que se ahorra es teclear el reparto de una transferencia que cubre
        cuatro entregas.

        Si sobra dinero, sobra y se ve. Un abono que no calza con nada suele
        ser un anticipo o un pago de algo que todavia no esta en el sistema, y
        forzarlo a cuadrar seria inventar la deuda que falta.
        """
        Imputacion = self.env['agrogood.payment.allocation']
        creadas = 0
        for m in self:
            if not m.partner_id:
                continue
            queda = m.amount_unapplied
            for orden in m._ordenes_abiertas():
                if m.currency_id.is_zero(queda) or queda <= 0:
                    break
                debe = orden.agrogood_due_amount
                if debe <= 0:
                    continue
                importe = min(queda, debe)
                Imputacion.create({
                    'movement_id': m.id, 'order_id': orden.id,
                    'amount': importe,
                })
                queda -= importe
                creadas += 1
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success' if creadas else 'warning',
                'message': _("%(n)s imputaciones creadas.", n=creadas) if creadas
                else _("No hay ninguna orden de compra pendiente a la que "
                       "imputar esto. Puede ser un anticipo, o un cobro de algo "
                       "que todavia no esta cargado en el sistema."),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
