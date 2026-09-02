from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ESTADO_PARADA = [
    ('pending', "Pendiente"),
    ('on_the_way', "En camino"),
    ('arrived', "Llegue"),
    ('delivered', "Entregado"),
    ('not_delivered', "No entregado"),
    ('rescheduled', "Reprogramado"),
]

MOTIVOS_FALLO = [
    ('customer_absent', "Cliente no recibio"),
    ('wrong_address', "Direccion incorrecta"),
    ('closed', "Local cerrado"),
    ('refused', "Cliente rechazo la mercaderia"),
    ('vehicle_issue', "Problema con el vehiculo"),
    ('other', "Otro"),
]


class AgrogoodRouteStop(models.Model):
    """Una entrega dentro de una ruta, con su evidencia.

    La parada apunta al albaran, nunca lo reemplaza: el movimiento de stock lo
    sigue haciendo Odoo al validar. Lo que la parada aporta es el orden, la
    ventana horaria y lo que ocurrio realmente al llegar.
    """

    _name = 'agrogood.route.stop'
    _description = 'Parada de ruta'
    _order = 'route_id, sequence, id'

    route_id = fields.Many2one(
        comodel_name='agrogood.route', string="Ruta",
        required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(string="Orden", default=10)
    picking_id = fields.Many2one(
        comodel_name='stock.picking', string="Albaran",
        required=True, ondelete='cascade', index=True,
    )
    partner_id = fields.Many2one(
        related='picking_id.partner_id', string="Cliente", store=True,
    )
    sale_order_id = fields.Many2one(
        related='picking_id.sale_id', string="Pedido", store=True,
    )

    # --- Donde y cuando -------------------------------------------------
    street = fields.Char(related='partner_id.street', string="Direccion")
    city = fields.Char(related='partner_id.city', string="Ciudad")
    phone = fields.Char(related='partner_id.phone', string="Telefono")
    latitude = fields.Float(related='partner_id.partner_latitude', digits=(10, 7))
    longitude = fields.Float(related='partner_id.partner_longitude', digits=(10, 7))
    scheduled_time = fields.Char(
        string="Horario comprometido",
        compute='_compute_scheduled_time', store=True,
        help="Franja acordada con el cliente en el pedido.",
    )
    delivery_note = fields.Char(
        related='sale_order_id.agrogood_delivery_note',
        string="Indicaciones",
    )

    # --- Que lleva -------------------------------------------------------
    line_summary = fields.Text(
        string="Productos", compute='_compute_line_summary',
        help="Resumen de lo que hay que entregar, para que el conductor lo "
             "compruebe sin abrir el albaran.",
    )
    estimated_weight = fields.Float(
        string="Peso estimado (kg)", compute='_compute_estimated_weight', store=True,
    )

    # --- Que paso --------------------------------------------------------
    state = fields.Selection(
        selection=ESTADO_PARADA, default='pending', required=True, index=True,
    )
    failure_reason = fields.Selection(
        selection=MOTIVOS_FALLO, string="Motivo",
    )
    arrival_time = fields.Datetime(string="Hora de llegada", readonly=True)
    delivery_time = fields.Datetime(string="Hora de entrega", readonly=True)
    received_by = fields.Char(string="Recibido por")
    signature = fields.Binary(string="Firma", attachment=True)
    photo = fields.Image(string="Fotografia", max_width=1280, max_height=1280)
    stop_note = fields.Text(string="Observaciones del conductor")
    gps_latitude = fields.Float(string="Latitud registrada", digits=(10, 7), readonly=True)
    gps_longitude = fields.Float(string="Longitud registrada", digits=(10, 7), readonly=True)

    reschedule_date = fields.Date(
        string="Se reprograma para",
        help="El dia en que se vuelve a intentar la entrega.",
    )

    company_id = fields.Many2one(related='route_id.company_id', store=True)

    # Antes habia una restriccion SQL de un albaran por parada. Impedia lo
    # unico que hace falta cuando una entrega falla: volver a intentarla otro
    # dia. Por eso "reprogramar" solo ponia una etiqueta y la entrega quedaba
    # colgada hasta que alguien la veia en el escritorio.
    #
    # Ahora se permite mas de una parada por albaran siempre que las anteriores
    # esten REPROGRAMADAS. Una parada reprogramada es historia -se intento ese
    # dia y no se pudo-; las demas retienen el albaran, porque un albaran en
    # dos rutas vivas a la vez es una entrega que sale dos veces.
    @api.constrains('picking_id', 'state')
    def _check_una_ruta_viva(self):
        for s in self:
            if not s.picking_id or s.state == 'rescheduled':
                continue
            otras = self.search([
                ('picking_id', '=', s.picking_id.id),
                ('id', '!=', s.id),
                ('state', '!=', 'rescheduled'),
            ])
            if otras:
                raise ValidationError(_(
                    "%(albaran)s ya esta en la ruta %(ruta)s. Una entrega no "
                    "puede salir en dos rutas a la vez.",
                    albaran=s.picking_id.name,
                    ruta=otras[0].route_id.display_name))

    # ------------------------------------------------------------------

    @api.depends('sale_order_id.agrogood_delivery_slot',
                 'sale_order_id.commitment_date')
    def _compute_scheduled_time(self):
        etiquetas = {'morning': "Manana", 'afternoon': "Tarde",
                     'specific': "Hora concreta"}
        for s in self:
            pedido = s.sale_order_id
            if pedido.agrogood_delivery_slot == 'specific' and pedido.commitment_date:
                s.scheduled_time = fields.Datetime.context_timestamp(
                    s, pedido.commitment_date).strftime('%H:%M')
            elif pedido.agrogood_delivery_slot:
                s.scheduled_time = etiquetas.get(pedido.agrogood_delivery_slot)
            else:
                s.scheduled_time = False

    def _compute_line_summary(self):
        for s in self:
            lineas = s.picking_id.move_ids.filtered(lambda m: m.state != 'cancel')
            s.line_summary = "\n".join(
                f"{m.quantity or m.product_uom_qty:g} {m.product_uom.name} · "
                f"{m.product_id.name}"
                for m in lineas
            )

    @api.depends('picking_id.move_ids.quantity',
                 'picking_id.move_ids.product_uom_qty')
    def _compute_estimated_weight(self):
        """Peso de la parada, para saber si cabe en el camion.

        En productos de peso variable la cantidad YA esta en kilos, asi que es
        el peso. En el resto se multiplica por el peso unitario del producto,
        que puede estar sin informar: entonces suma cero y el total se queda
        corto. Es una estimacion para repartir carga, no una bascula.
        """
        categoria_peso = self.env.ref('uom.product_uom_categ_kgm',
                                      raise_if_not_found=False)
        for s in self:
            total = 0.0
            for m in s.picking_id.move_ids.filtered(lambda m: m.state != 'cancel'):
                cantidad = m.quantity or m.product_uom_qty
                if categoria_peso and m.product_uom.category_id == categoria_peso:
                    total += m.product_uom._compute_quantity(
                        cantidad, self.env.ref('uom.product_uom_kgm'))
                else:
                    total += cantidad * (m.product_id.weight or 0.0)
            s.estimated_weight = total

    @api.constrains('state', 'failure_reason')
    def _check_failure_reason(self):
        for s in self:
            if s.state in ('not_delivered', 'rescheduled') and not s.failure_reason:
                raise ValidationError(_(
                    "Indica por que no se entrego en %s.",
                    s.partner_id.display_name,
                ))

    # ------------------------------------------------------------------
    # Acciones del conductor
    # ------------------------------------------------------------------

    def action_on_the_way(self):
        self.write({'state': 'on_the_way'})
        return True

    def action_arrived(self):
        self.write({'state': 'arrived', 'arrival_time': fields.Datetime.now()})
        return True

    def action_delivered(self):
        """Valida el albaran y solo entonces marca la parada como entregada.

        Aqui SI se valida el albaran, al contrario que al terminar una
        preparacion. La diferencia es que el conductor esta delante del
        cliente: si dice que entrego, la mercaderia ya salio y el stock tiene
        que reflejarlo.

        El ORDEN importa y no es casual. Marcar la parada primero y validar
        despues deja un estado imposible cuando la validacion falla -por
        ejemplo por un peso fuera de tolerancia-: la parada dice entregada y el
        stock nunca se movio. Y como quien llama captura el error para
        mostrarlo, no hay rollback que deshaga el escrito. Validando primero,
        un fallo deja todo como estaba.
        """
        for s in self:
            if s.state == 'delivered':
                continue
            if s.picking_id.state not in ('done', 'cancel'):
                for mv in s.picking_id.move_ids.filtered(
                        lambda m: m.state not in ('done', 'cancel')):
                    if not mv.quantity:
                        mv.quantity = mv.product_uom_qty
                    mv.picked = True
                s.picking_id.button_validate()
            s.write({
                'state': 'delivered',
                'delivery_time': fields.Datetime.now(),
                'arrival_time': s.arrival_time or fields.Datetime.now(),
            })
        return True

    def action_not_delivered(self):
        for s in self:
            if not s.failure_reason:
                raise UserError(_(
                    "Indica primero por que no se pudo entregar en %s.",
                    s.partner_id.display_name,
                ))
            s.state = 'not_delivered'
            # La excepcion se propaga al pedido para que Ventas la vea sin
            # tener que entrar en la ruta.
            if s.sale_order_id:
                s.sale_order_id.write({
                    'agrogood_exception': s._exception_for_sale(),
                    'agrogood_exception_note': s.stop_note or dict(
                        MOTIVOS_FALLO)[s.failure_reason],
                })
        return True

    def action_rescheduled(self):
        """Deja la entrega para otro dia, y la devuelve al reparto de ese dia.

        Exige la fecha ademas del motivo. Sin fecha, reprogramar es solo una
        etiqueta: la entrega desaparece de la ruta de hoy, no aparece en la de
        ningun otro dia, y se queda esperando a que alguien se acuerde. Con
        fecha, el albaran vuelve a la lista de Logistica de ese dia y se arma
        una ruta nueva con el como con cualquier otro.
        """
        for s in self:
            if not s.failure_reason:
                raise UserError(_(
                    "Indica el motivo de la reprogramacion en %s.",
                    s.partner_id.display_name,
                ))
            if not s.reschedule_date:
                raise UserError(_(
                    "Di para que dia se reprograma la entrega de %s. Sin "
                    "fecha se quedaria sin ruta y sin nadie esperandola.",
                    s.partner_id.display_name,
                ))
            hoy = fields.Date.context_today(s)
            if s.reschedule_date <= hoy:
                raise UserError(_(
                    "La entrega de %(cliente)s se reprograma para el "
                    "%(fecha)s, que ya paso o es hoy mismo. Si es para hoy, no "
                    "hace falta reprogramarla.",
                    cliente=s.partner_id.display_name,
                    fecha=s.reschedule_date))
            s.state = 'rescheduled'
            # El albaran se mueve al dia nuevo. Es lo que lo devuelve a la
            # lista de Logistica: sin esto seguiria fechado para hoy y saldria
            # como atrasado todos los dias hasta que alguien lo tocara.
            if s.picking_id:
                s.picking_id.scheduled_date = fields.Datetime.to_datetime(
                    s.reschedule_date)
            if s.sale_order_id:
                s.sale_order_id.write({
                    'agrogood_exception': 'rescheduled',
                    'agrogood_exception_note': _(
                        "Reprogramada para el %(fecha)s. %(motivo)s",
                        fecha=s.reschedule_date,
                        motivo=s.stop_note or dict(
                            MOTIVOS_FALLO)[s.failure_reason]),
                })
                s.sale_order_id.message_post(body=_(
                    "Entrega reprogramada para el %(fecha)s: %(motivo)s",
                    fecha=s.reschedule_date,
                    motivo=s.stop_note or dict(
                        MOTIVOS_FALLO)[s.failure_reason]))
        return True

    def _exception_for_sale(self):
        """Traduce el motivo del conductor a la excepcion del pedido."""
        self.ensure_one()
        equivalencias = {
            'customer_absent': 'customer_absent',
            'wrong_address': 'wrong_address',
            'closed': 'customer_absent',
            'refused': 'delivery_incident',
            'vehicle_issue': 'delivery_incident',
            'other': 'delivery_incident',
        }
        return equivalencias.get(self.failure_reason, 'delivery_incident')
