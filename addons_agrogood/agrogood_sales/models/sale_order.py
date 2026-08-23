from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Las once etapas del pedido. El orden importa: se usa para ordenar la vista y
# para saber si un pedido esta atrasado respecto de donde deberia estar.
ESTADO_OPERATIVO = [
    ('draft', "Pedido registrado"),
    ('awaiting_stock', "Pendiente de stock"),
    ('to_pick', "Pendiente de preparacion"),
    ('picking', "En preparacion"),
    ('picked', "Preparado"),
    ('to_dispatch', "Pendiente de despacho"),
    ('in_route', "En ruta"),
    ('delivered', "Entregado"),
    ('invoiced', "Facturado"),
    ('closed', "Cerrado"),
    ('cancelled', "Cancelado"),
]

EXCEPCIONES = [
    ('shortage', "Producto faltante"),
    ('incomplete', "Pedido incompleto"),
    ('customer_absent', "Cliente no recibio"),
    ('wrong_address', "Direccion incorrecta"),
    ('rescheduled', "Reprogramado"),
    ('delivery_incident', "Incidencia de entrega"),
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # Origen y agenda
    # ------------------------------------------------------------------

    agrogood_source = fields.Selection(
        selection=[
            ('whatsapp', "WhatsApp"),
            ('phone', "Telefono"),
            ('in_person', "Presencial"),
            ('portal', "Portal"),
            ('recurring', "Pedido habitual"),
        ],
        string="Origen del pedido",
        default='whatsapp',
        tracking=True,
        help="Por donde llego el pedido. Permite medir por que canal entra el "
             "negocio antes de decidir en cual invertir.",
    )
    agrogood_delivery_slot = fields.Selection(
        selection=[
            ('morning', "Manana"),
            ('afternoon', "Tarde"),
            ('specific', "Hora concreta"),
        ],
        string="Franja de entrega",
        tracking=True,
    )
    agrogood_delivery_note = fields.Char(
        string="Indicaciones de entrega",
        help="Restricciones del cliente: hora concreta, persona que recibe, "
             "acceso al local. Lo lee el conductor en la PWA.",
    )
    agrogood_business_line_id = fields.Many2one(
        related='partner_id.agrogood_business_line_id',
        string="Linea comercial",
        store=True,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Estado operativo
    # ------------------------------------------------------------------

    agrogood_state = fields.Selection(
        selection=ESTADO_OPERATIVO,
        string="Estado operativo",
        compute='_compute_agrogood_state',
        store=True,
        index=True,
        help="Donde esta el pedido en la operacion. Se calcula a partir del "
             "estado real del pedido, sus albaranes y sus facturas.",
    )
    agrogood_exception = fields.Selection(
        selection=EXCEPCIONES,
        string="Excepcion",
        tracking=True,
        copy=False,
        help="Lo que se salio del curso normal. Es informacion nueva: no se "
             "deduce de ningun otro dato del sistema, alguien tiene que "
             "registrarla.",
    )
    agrogood_exception_note = fields.Char(string="Detalle de la excepcion", copy=False)
    agrogood_closed = fields.Boolean(
        string="Cerrado",
        copy=False,
        help="Marca manual de cierre. Un pedido facturado sigue abierto hasta "
             "que Ventas da por terminada cualquier gestion pendiente.",
    )

    @api.depends('state', 'agrogood_closed', 'invoice_status',
                 'picking_ids.state', 'order_line.agrogood_shortage_qty')
    def _compute_agrogood_state(self):
        """Deriva la etapa operativa de los datos que ya existen.

        Nada aqui se escribe a mano. Cada modulo posterior puede afinar el
        resultado sobreescribiendo `_agrogood_state_from_logistics`, que es el
        punto de extension previsto para rutas y sesiones de picking.
        """
        for order in self:
            order.agrogood_state = order._agrogood_compute_state()

    def _agrogood_compute_state(self):
        self.ensure_one()
        if self.state == 'cancel':
            return 'cancelled'
        if self.agrogood_closed:
            return 'closed'
        if self.state in ('draft', 'sent'):
            return 'draft'

        # A partir de aqui el pedido esta confirmado.
        if self.invoice_status == 'invoiced':
            return 'invoiced'

        pickings = self.picking_ids.filtered(lambda p: p.state != 'cancel')
        if pickings and all(p.state == 'done' for p in pickings):
            return 'delivered'

        desde_logistica = self._agrogood_state_from_logistics()
        if desde_logistica:
            return desde_logistica

        if any(line.agrogood_shortage_qty > 0 for line in self.order_line):
            return 'awaiting_stock'
        if any(p.state == 'assigned' for p in pickings):
            return 'to_pick'
        if pickings:
            return 'awaiting_stock'
        return 'draft'

    def _agrogood_state_from_logistics(self):
        """Punto de extension para picking y rutas.

        Devuelve None mientras no existan esos modulos. `agrogood_picking_ops`
        devolvera 'picking' o 'picked' segun la sesion del Picker, y
        `agrogood_logistics` devolvera 'to_dispatch' o 'in_route' segun la ruta
        asignada. Se declara ya para que el calculo no haya que reescribirlo
        despues.
        """
        self.ensure_one()
        return None

    # ------------------------------------------------------------------
    # Faltantes
    # ------------------------------------------------------------------

    agrogood_has_shortage = fields.Boolean(
        string="Con faltantes",
        compute='_compute_agrogood_shortage',
        store=True,
    )
    agrogood_shortage_count = fields.Integer(
        string="Lineas con faltante",
        compute='_compute_agrogood_shortage',
        store=True,
    )

    @api.depends('order_line.agrogood_shortage_qty')
    def _compute_agrogood_shortage(self):
        for order in self:
            faltan = order.order_line.filtered(lambda l: l.agrogood_shortage_qty > 0)
            order.agrogood_shortage_count = len(faltan)
            order.agrogood_has_shortage = bool(faltan)

    # ------------------------------------------------------------------
    # Captura rapida
    # ------------------------------------------------------------------

    def action_agrogood_repeat_last_order(self):
        """Copia las lineas del ultimo pedido del cliente.

        La mayoria de los pedidos de un distribuidor son variaciones del
        anterior. Traerlo entero y corregir lo que cambia es mucho mas rapido
        -y comete menos errores- que teclear veinte lineas mientras se lee un
        chat.

        Se copian producto y cantidad, nunca el precio: el precio lo resuelve
        la tarifa vigente hoy. Repetir el precio del pedido anterior seria
        saltarse la lista de precios de la semana.
        """
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            raise UserError(_("Solo se pueden traer lineas a un pedido en borrador."))
        if not self.partner_id:
            raise UserError(_("Elige primero el cliente."))

        anterior = self.search([
            ('partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('state', 'in', ('sale', 'done')),
            ('id', '!=', self.id),
        # 'id desc' desempata: dos pedidos del mismo dia comparten date_order
        # y sin criterio adicional 'el ultimo' queda indefinido.
        ], order='date_order desc, id desc', limit=1)
        if not anterior:
            raise UserError(_(
                "%s no tiene pedidos anteriores confirmados.",
                self.partner_id.display_name,
            ))

        existentes = self.order_line.product_id
        nuevas = [
            (0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'product_uom': line.product_uom.id,
            })
            for line in anterior.order_line
            if line.product_id and not line.display_type and line.product_id not in existentes
        ]
        if not nuevas:
            raise UserError(_(
                "El pedido %s no aporta productos nuevos: ya estan todos en este pedido.",
                anterior.name,
            ))
        self.write({'order_line': nuevas})
        self.agrogood_source = 'recurring'
        self.message_post(body=_(
            "Se trajeron %(n)s lineas del pedido %(ref)s del %(fecha)s. "
            "Los precios se recalcularon con la tarifa vigente.",
            n=len(nuevas), ref=anterior.name,
            fecha=fields.Date.to_string(anterior.date_order.date()),
        ))
        return True

    # ------------------------------------------------------------------
    # Excepciones y cierre
    # ------------------------------------------------------------------

    def action_agrogood_close(self):
        for order in self:
            if order.state not in ('sale', 'done'):
                raise UserError(_(
                    "Solo se cierra un pedido confirmado. %s esta en '%s'.",
                    order.name, order.state,
                ))
            order.agrogood_closed = True
        return True

    def action_agrogood_reopen(self):
        self.write({'agrogood_closed': False})
        return True

    @api.onchange('partner_id')
    def _onchange_partner_agrogood_warning(self):
        """Avisa a Ventas de que a este cliente aun no se le puede facturar."""
        if self.partner_id and self.partner_id.agrogood_vat_pending:
            return {'warning': {
                'title': _("Cliente sin RUT"),
                'message': _(
                    "%s no tiene RUT registrado. Puedes tomarle el pedido y "
                    "despacharlo, pero no se le podra emitir factura hasta que "
                    "se complete.",
                    self.partner_id.display_name,
                ),
            }}
