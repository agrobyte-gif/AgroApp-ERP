from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

# Los nueve estados por los que pasa una solicitud. El orden es el de la
# pizarra: se leen de izquierda a derecha como avanza el trabajo, y los cuatro
# desenlaces sin compra quedan al final.
ESTADOS = [
    ('pending', "Pendiente"),
    ('searching', "En busqueda"),
    ('quoting', "Cotizando"),
    ('purchased', "Comprado"),
    ('received', "Recibido"),
    ('partial', "Parcialmente encontrado"),
    ('not_found', "No encontrado"),
    ('rejected', "Rechazado"),
    ('cancelled', "Cancelado"),
]

# Estados en los que la solicitud ya no espera trabajo de Compras.
CERRADOS = ('received', 'not_found', 'rejected', 'cancelled')


class AgrogoodPurchaseRequest(models.Model):
    """Algo que hay que conseguir, con su ciclo de vida y su conversacion."""

    _name = 'agrogood.purchase.request'
    _description = 'Solicitud de compra'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, date_needed, id desc'

    name = fields.Char(
        required=True, copy=False, readonly=True, default=lambda self: _("Nueva"),
    )
    active = fields.Boolean(default=True)

    # --- Que se necesita -----------------------------------------------
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Producto",
        required=True,
        tracking=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string="Unidad",
        compute='_compute_product_uom_id',
        store=True,
        readonly=False,
    )
    qty_requested = fields.Float(
        string="Cantidad solicitada",
        required=True,
        default=1.0,
        digits='Product Unit of Measure',
        tracking=True,
    )
    qty_purchased = fields.Float(
        string="Cantidad conseguida",
        digits='Product Unit of Measure',
        tracking=True,
        help="Lo que finalmente se logro comprar. Si es menor que lo solicitado, "
             "la solicitud es parcial.",
    )

    # --- Para quien y para cuando --------------------------------------
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Cliente que lo solicita",
        tracking=True,
        help="Deja ver para quien se esta comprando. Un cliente habitual que "
             "espera puede cambiar la prioridad de la busqueda.",
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string="Pedido de origen",
        readonly=True,
        ondelete='set null',
    )
    sale_order_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string="Linea de origen",
        readonly=True,
        ondelete='set null',
    )
    date_needed = fields.Date(
        string="Se necesita para",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    priority = fields.Selection(
        selection=[('0', "Normal"), ('1', "Alta"), ('2', "Urgente")],
        string="Prioridad",
        default='0',
        tracking=True,
    )

    # --- Motivo y detalle ----------------------------------------------
    reason = fields.Selection(
        selection=[
            ('shortage', "Faltante de pedido"),
            ('restock', "Reposicion de stock"),
            ('client_request', "Peticion del cliente"),
            ('new_product', "Producto nuevo"),
            ('other', "Otro"),
        ],
        string="Motivo",
        default='shortage',
        required=True,
        tracking=True,
    )
    expected_price = fields.Monetary(
        string="Valor esperado",
        currency_field='currency_id',
        help="Referencia de lo que deberia costar. Ayuda a decidir si una "
             "cotizacion es razonable.",
    )
    note = fields.Text(string="Observaciones")
    state_note = fields.Char(
        string="Respuesta de Compras",
        tracking=True,
        help="Respuesta corta visible en la pizarra: donde se consiguio, por que "
             "no se encontro, a que precio.",
    )

    # --- Gestion --------------------------------------------------------
    state = fields.Selection(
        selection=ESTADOS, default='pending', required=True, tracking=True, index=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string="Responsable",
        tracking=True,
        default=lambda self: self._default_user_id(),
        help="Quien gestiona la busqueda. Por defecto, el Encargado de Compras.",
    )
    requested_by_id = fields.Many2one(
        comodel_name='res.users',
        string="Solicitado por",
        default=lambda self: self.env.user,
        readonly=True,
    )
    purchase_order_id = fields.Many2one(
        comodel_name='purchase.order',
        string="Orden de compra",
        readonly=True,
        ondelete='set null',
    )
    supplier_id = fields.Many2one(
        comodel_name='res.partner',
        string="Proveedor",
        tracking=True,
    )

    company_id = fields.Many2one(
        comodel_name='res.company', required=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    color = fields.Integer(string="Color")

    is_late = fields.Boolean(
        string="Atrasada", compute='_compute_is_late', search='_search_is_late',
    )
    qty_received = fields.Float(
        string="Recibido", compute='_compute_qty_received',
        help="Cuanto de lo pedido ya llego a bodega. Se lee de la orden de "
             "compra, que Odoo actualiza al validar cada recepcion.",
    )

    # ------------------------------------------------------------------
    # Calculos
    # ------------------------------------------------------------------

    @api.model
    def _default_user_id(self):
        """Asigna por defecto a alguien de Compras, no a quien crea la solicitud.

        Quien la crea suele ser Logistica; dejarsela asignada a si mismo haria
        que la pizarra de Compras naciera vacia.
        """
        grupo = self.env.ref('agrogood_base.group_agrogood_purchase',
                             raise_if_not_found=False)
        if grupo and grupo.users:
            return grupo.users[0]
        return self.env.user

    @api.depends('product_id')
    def _compute_product_uom_id(self):
        for req in self:
            req.product_uom_id = req.product_id.uom_id

    def _compute_is_late(self):
        hoy = fields.Date.context_today(self)
        for req in self:
            req.is_late = bool(
                req.date_needed and req.date_needed < hoy and req.state not in CERRADOS
            )

    @api.depends('purchase_order_id.order_line.qty_received', 'product_id')
    def _compute_qty_received(self):
        for req in self:
            po = req.purchase_order_id
            lineas = po.order_line.filtered(
                lambda l: l.product_id == req.product_id) if po else False
            req.qty_received = sum(lineas.mapped('qty_received')) if lineas else 0.0

    def _search_is_late(self, operator, value):
        hoy = fields.Date.context_today(self)
        atrasadas = ['&', ('date_needed', '<', hoy), ('state', 'not in', CERRADOS)]
        if (operator == '=' and value) or (operator == '!=' and not value):
            return atrasadas
        return ['!'] + atrasadas

    # ------------------------------------------------------------------
    # Creacion
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("Nueva")) == _("Nueva"):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'agrogood.purchase.request') or _("Nueva")
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Transiciones
    # ------------------------------------------------------------------

    def _cambiar_estado(self, nuevo):
        etiquetas = dict(ESTADOS)
        for req in self:
            if req.state == nuevo:
                continue
            anterior = etiquetas.get(req.state)
            req.state = nuevo
            req.message_post(body=_(
                "Estado: %(antes)s -> %(despues)s",
                antes=anterior, despues=etiquetas[nuevo],
            ))
        return True

    def action_search(self):
        return self._cambiar_estado('searching')

    def action_quote(self):
        return self._cambiar_estado('quoting')

    def action_not_found(self):
        return self._cambiar_estado('not_found')

    def action_reject(self):
        return self._cambiar_estado('rejected')

    def action_cancel(self):
        return self._cambiar_estado('cancelled')

    def action_reset(self):
        return self._cambiar_estado('pending')

    def action_mark_received(self):
        for req in self:
            if req.state not in ('purchased', 'partial'):
                raise UserError(_(
                    "Solo se marca como recibida una solicitud comprada. "
                    "%(nombre)s esta en '%(estado)s'.",
                    nombre=req.name, estado=dict(ESTADOS)[req.state],
                ))
        return self._cambiar_estado('received')

    def _cerrar_por_recepcion(self):
        """Cierra la solicitud cuando Bodega recibe lo que Compras pidio.

        Es el cruce que faltaba entre las dos pantallas. Sin el, una solicitud
        se queda en 'Comprado' para siempre aunque la mercaderia ya haya
        llegado y este en la bodega: la pizarra de Compras y el control de
        Bodega vivian separados, y alguien tenia que acordarse de marcar a mano
        lo que el sistema ya sabia.

        Lo recibido se lee de la orden de compra -Odoo ya lo lleva por linea al
        validar la recepcion-, no del picking suelto: una compra puede llegar
        en dos viajes, y lo que cierra la solicitud es el total, no el primer
        camion.

        Solo se cierra si llego TODO. Si llego de menos, se anota cuanto y la
        solicitud sigue abierta a la espera del resto: dar por recibida media
        entrega esconderia lo que todavia falta conseguir. Reusar el estado
        'Parcialmente encontrado' seria mentir -ese es de la feria, no de la
        bodega-, asi que un recibo parcial deja la solicitud en 'Comprado' con
        una nota, no la mueve.
        """
        for req in self:
            po = req.purchase_order_id
            if not po or req.state != 'purchased':
                continue
            lineas = po.order_line.filtered(
                lambda l: l.product_id == req.product_id)
            if not lineas:
                continue
            recibido = sum(lineas.mapped('qty_received'))
            pedido = req.qty_purchased or sum(lineas.mapped('product_qty'))
            rounding = req.product_uom_id.rounding or 0.01
            if float_compare(recibido, 0.0, precision_rounding=rounding) <= 0:
                continue
            uom = req.product_uom_id.name
            if float_compare(recibido, pedido, precision_rounding=rounding) >= 0:
                req.state = 'received'
                req.message_post(body=_(
                    "Recibido en bodega: %(qty)s %(uom)s. La solicitud se "
                    "cierra sola.",
                    qty="{:g}".format(recibido), uom=uom))
            else:
                req.message_post(body=_(
                    "Recibido parcial en bodega: %(r)s de %(p)s %(uom)s. Sigue "
                    "abierta a la espera del resto.",
                    r="{:g}".format(recibido), p="{:g}".format(pedido),
                    uom=uom))

    # ------------------------------------------------------------------
    # Paso a orden de compra
    # ------------------------------------------------------------------

    def action_create_purchase_order(self):
        """Convierte las solicitudes seleccionadas en ordenes de compra.

        Se agrupan por proveedor: pedirle tres productos al mismo proveedor son
        tres lineas de una orden, no tres ordenes. Es como se compra de verdad.
        """
        sin_proveedor = self.filtered(lambda r: not r.supplier_id)
        if sin_proveedor:
            raise UserError(_(
                "Falta indicar el proveedor en: %s",
                ", ".join(sin_proveedor.mapped('name')),
            ))
        ya_convertidas = self.filtered('purchase_order_id')
        if ya_convertidas:
            raise UserError(_(
                "Estas solicitudes ya tienen orden de compra: %s",
                ", ".join(ya_convertidas.mapped('name')),
            ))

        ordenes = self.env['purchase.order']
        for proveedor in self.supplier_id:
            solicitudes = self.filtered(lambda r: r.supplier_id == proveedor)
            orden = self.env['purchase.order'].create({
                'partner_id': proveedor.id,
                'company_id': solicitudes[0].company_id.id,
                'origin': ", ".join(solicitudes.mapped('name')),
                'order_line': [
                    (0, 0, {
                        'product_id': req.product_id.id,
                        'product_qty': req.qty_requested,
                        'product_uom': req.product_uom_id.id,
                        'price_unit': req.expected_price or 0.0,
                        'date_planned': fields.Datetime.to_datetime(req.date_needed),
                        'name': req.product_id.display_name,
                    })
                    for req in solicitudes
                ],
            })
            for req in solicitudes:
                req.write({
                    'purchase_order_id': orden.id,
                    'state': 'purchased',
                    'qty_purchased': req.qty_requested,
                })
                req.message_post(body=_(
                    "Convertida en la orden de compra %(orden)s a %(proveedor)s.",
                    orden=orden.name, proveedor=proveedor.display_name,
                ))
            ordenes |= orden

        return {
            'type': 'ir.actions.act_window',
            'name': _("Ordenes de compra generadas"),
            'res_model': 'purchase.order',
            'view_mode': 'form' if len(ordenes) == 1 else 'list,form',
            'res_id': ordenes.id if len(ordenes) == 1 else False,
            'domain': [('id', 'in', ordenes.ids)],
        }

    def action_view_purchase_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_order_id.id,
        }

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }
