from datetime import timedelta

from odoo import _, api, fields, models

MOTIVOS = [
    ('same_weekday', "Compro este dia la semana pasada"),
    ('expected_day', "Le toca comprar segun su frecuencia"),
    ('volume_drop', "Esta comprando bastante menos"),
    ('inactive', "Lleva demasiado sin comprar"),
    ('manual', "Seguimiento manual"),
]

ESTADOS = [
    ('pending', "Pendiente de contactar"),
    ('contacted', "Contactado"),
    ('order_created', "Pedido generado"),
    ('not_interested', "No interesado"),
    ('rescheduled', "Reprogramado"),
    ('no_answer', "Sin respuesta"),
]

ABIERTOS = ('pending', 'contacted', 'rescheduled')


class AgrogoodFollowup(models.Model):
    """Un cliente al que hay que llamar hoy, y por que.

    Es la salida del motor de reactivacion: convierte el historial de ventas en
    una lista corta de llamadas concretas, en lugar de un informe que nadie
    abre.
    """

    _name = 'agrogood.followup'
    _description = 'Seguimiento comercial'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, priority desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    partner_id = fields.Many2one(
        comodel_name='res.partner', string="Cliente",
        required=True, index=True, tracking=True,
    )
    date = fields.Date(
        string="Fecha", required=True, default=fields.Date.context_today, index=True,
    )
    reason = fields.Selection(
        selection=MOTIVOS, string="Motivo", required=True, index=True,
    )
    state = fields.Selection(
        selection=ESTADOS, default='pending', required=True,
        tracking=True, index=True,
    )
    priority = fields.Selection(
        selection=[('0', "Normal"), ('1', "Alta")], default='0',
    )
    user_id = fields.Many2one(
        comodel_name='res.users', string="Responsable",
        default=lambda self: self._default_user_id(), tracking=True,
    )

    # Datos que Ventas necesita tener delante al llamar, sin abrir nada mas.
    business_line_id = fields.Many2one(
        related='partner_id.agrogood_business_line_id', store=True,
        string="Linea comercial",
    )
    phone = fields.Char(related='partner_id.phone', string="Telefono")
    city = fields.Char(related='partner_id.city', string="Ciudad")
    last_order_id = fields.Many2one(
        comodel_name='sale.order', string="Ultimo pedido", readonly=True,
    )
    last_order_date = fields.Date(
        related='partner_id.agrogood_last_order_date', string="Ultima compra",
    )
    last_order_amount = fields.Monetary(
        string="Importe del ultimo pedido", readonly=True,
        currency_field='currency_id',
    )
    last_order_products = fields.Char(string="Llevo", readonly=True)
    top_products = fields.Char(
        related='partner_id.agrogood_top_products', string="Suele llevar",
    )
    days_since_order = fields.Integer(
        related='partner_id.agrogood_days_since_order', string="Dias sin comprar",
    )
    avg_ticket = fields.Monetary(
        related='partner_id.agrogood_avg_ticket', string="Ticket medio",
        currency_field='currency_id',
    )
    customer_status = fields.Selection(
        related='partner_id.agrogood_customer_status', string="Situacion",
    )
    currency_id = fields.Many2one(
        related='partner_id.currency_id', string="Moneda",
    )

    sale_order_id = fields.Many2one(
        comodel_name='sale.order', string="Pedido generado", readonly=True,
    )
    note = fields.Text(string="Notas de la gestion")
    company_id = fields.Many2one(
        comodel_name='res.company', required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('uniq_dia', 'unique(partner_id, date, reason)',
         "Ya existe un seguimiento de este cliente por este motivo hoy."),
    ]

    # ------------------------------------------------------------------

    @api.model
    def _default_user_id(self):
        grupo = self.env.ref('agrogood_base.group_agrogood_sales',
                             raise_if_not_found=False)
        if grupo and grupo.users:
            return grupo.users[0]
        return self.env.user

    @api.depends('partner_id.name', 'reason')
    def _compute_name(self):
        etiquetas = dict(MOTIVOS)
        for f in self:
            f.name = f"{f.partner_id.name} · {etiquetas.get(f.reason, '')}" \
                if f.partner_id else ""

    # ------------------------------------------------------------------
    # Generacion
    # ------------------------------------------------------------------

    @api.model
    def _cron_generar_seguimientos(self):
        """Arma la lista de llamadas del dia.

        Se ejecuta cada manana. No crea nada si el cliente ya tiene un
        seguimiento abierto: insistir dos veces el mismo dia por motivos
        distintos hace que Ventas deje de mirar la lista.
        """
        Socio = self.env['res.partner']
        hoy = fields.Date.context_today(self)
        creados = self.browse()

        # Clientes con un seguimiento ya abierto: se dejan en paz.
        ocupados = set(self.search([('state', 'in', ABIERTOS)]).mapped('partner_id.id'))

        # Tampoco se insiste con un motivo que ya se gestiono hace poco. Sin
        # esto, un cliente inactivo reaparece cada manana aunque Ventas ya haya
        # anotado que no le interesa, y la lista pierde toda credibilidad.
        reciente = hoy - timedelta(days=14)
        gestionados = {
            (f.partner_id.id, f.reason)
            for f in self.search([('date', '>=', reciente)])
        }

        # Los que ya pidieron hoy tampoco necesitan llamada.
        pidieron_hoy = set(self.env['sale.order'].search([
            ('state', 'in', ('sale', 'done')),
            ('date_order', '>=', fields.Datetime.to_string(
                fields.Datetime.now().replace(hour=0, minute=0, second=0))),
        ]).mapped('partner_id.commercial_partner_id.id'))

        candidatos = Socio.search([
            ('agrogood_business_line_id', '!=', False),
            ('parent_id', '=', False),
            ('agrogood_order_count', '>', 0),
        ])

        for socio in candidatos:
            if socio.id in ocupados or socio.id in pidieron_hoy:
                continue
            motivo, prioridad = self._agrogood_motivo_para(socio, hoy)
            if not motivo or (socio.id, motivo) in gestionados:
                continue
            creados |= self._agrogood_crear(socio, motivo, hoy, prioridad)

        # No se confirma la transaccion a mano: Odoo ya lo hace al terminar el
        # cron, y forzarlo aqui impediria deshacer una ejecucion de prueba.
        return len(creados)

    @api.model
    def _agrogood_motivo_para(self, socio, hoy):
        """Decide si hay que llamar hoy a este cliente, y por que.

        El orden de las comprobaciones es el orden de urgencia comercial: se
        devuelve el primer motivo que aplique, no todos. Un cliente aparece una
        vez en la lista, con la razon mas fuerte.
        """
        ultima = socio.agrogood_last_order_date
        if not ultima:
            return None, '0'
        dias = (hoy - ultima).days

        # 1. Compro justo este dia de la semana pasada y hoy no ha pedido.
        #    Es el patron mas fiable en distribucion: el cliente tiene un dia
        #    fijo y hoy se le ha pasado.
        if dias == 7:
            return 'same_weekday', '1'

        # 2. Cayo su volumen de forma clara aunque siga comprando.
        if socio.agrogood_volume_trend <= -30 and socio.agrogood_order_count >= 4:
            return 'volume_drop', '1'

        # 3. Se paso de su propia frecuencia.
        frecuencia = socio.agrogood_avg_days_between or 7.0
        if socio.agrogood_customer_status == 'at_risk' and dias >= frecuencia * 1.5:
            return 'expected_day', '1'
        if socio.agrogood_customer_status in ('inactive', 'lost'):
            return 'inactive', '0'
        return None, '0'

    @api.model
    def _agrogood_crear(self, socio, motivo, fecha, prioridad='0'):
        ultimo = self.env['sale.order'].search([
            ('partner_id', 'child_of', socio.id),
            ('state', 'in', ('sale', 'done')),
        ], order='date_order desc', limit=1)
        productos = ", ".join(
            ultimo.order_line.filtered(
                lambda l: l.product_id and not l.display_type
            ).mapped('product_id.name')[:5]
        )
        return self.create({
            'partner_id': socio.id,
            'date': fecha,
            'reason': motivo,
            'priority': prioridad,
            'last_order_id': ultimo.id or False,
            'last_order_amount': ultimo.amount_untaxed or 0.0,
            'last_order_products': productos,
        })

    # ------------------------------------------------------------------
    # Gestion
    # ------------------------------------------------------------------

    def action_contacted(self):
        self.write({'state': 'contacted'})
        return True

    def action_not_interested(self):
        self.write({'state': 'not_interested'})
        return True

    def action_no_answer(self):
        self.write({'state': 'no_answer'})
        return True

    def action_rescheduled(self):
        self.write({'state': 'rescheduled'})
        return True

    def action_create_order(self):
        """Abre un pedido nuevo con el ultimo pedido del cliente ya cargado.

        Es el atajo que da sentido a la lista: se llama al cliente, dice que si,
        y el pedido esta escrito antes de colgar. Los precios se recalculan con
        la tarifa vigente, nunca se copian del pedido anterior.
        """
        self.ensure_one()
        pedido = self.env['sale.order'].create({'partner_id': self.partner_id.id,
                                                'agrogood_source': 'recurring'})
        try:
            pedido.action_agrogood_repeat_last_order()
        except Exception:
            # Sin pedido anterior utilizable se abre igualmente en blanco: es
            # mejor que dejar a Ventas sin pantalla donde escribir.
            pass
        self.write({'state': 'order_created', 'sale_order_id': pedido.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': pedido.id,
        }

    def action_open_partner(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.partner_id.id,
        }
