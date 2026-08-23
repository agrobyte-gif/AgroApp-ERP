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

    company_id = fields.Many2one(related='route_id.company_id', store=True)

    _sql_constraints = [
        ('picking_uniq', 'unique(picking_id)',
         "Este albaran ya esta en una ruta."),
    ]

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
        """Marca la entrega y valida el albaran.

        Aqui SI se valida, al contrario que al terminar una preparacion. La
        diferencia es que el conductor esta delante del cliente: si dice que
        entrego, la mercaderia ya salio y el stock tiene que reflejarlo.
        """
        for s in self:
            if s.state == 'delivered':
                continue
            s.write({
                'state': 'delivered',
                'delivery_time': fields.Datetime.now(),
                'arrival_time': s.arrival_time or fields.Datetime.now(),
            })
            if s.picking_id.state not in ('done', 'cancel'):
                for mv in s.picking_id.move_ids.filtered(
                        lambda m: m.state not in ('done', 'cancel')):
                    if not mv.quantity:
                        mv.quantity = mv.product_uom_qty
                    mv.picked = True
                s.picking_id.button_validate()
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
        for s in self:
            if not s.failure_reason:
                raise UserError(_(
                    "Indica el motivo de la reprogramacion en %s.",
                    s.partner_id.display_name,
                ))
            s.state = 'rescheduled'
            if s.sale_order_id:
                s.sale_order_id.write({
                    'agrogood_exception': 'rescheduled',
                    'agrogood_exception_note': s.stop_note or dict(
                        MOTIVOS_FALLO)[s.failure_reason],
                })
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
