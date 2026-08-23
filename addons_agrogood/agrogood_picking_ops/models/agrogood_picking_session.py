from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AgrogoodPickingSession(models.Model):
    """La preparacion de un albaran por un Picker concreto, con sus tiempos.

    Existe porque `stock.picking` sabe QUE hay que preparar pero no QUIEN lo
    prepara, CUANDO empezo ni CUANTO tardo. Esas tres cosas son las que Felipe
    necesita para repartir carga y medir productividad, y no se pueden deducir
    de ningun dato del albaran.

    El estado de cada linea NO vive aqui: vive en `stock.move`. Duplicar las
    lineas en un modelo paralelo obligaria a mantener dos verdades en
    sincronia, y tarde o temprano dejarian de coincidir.
    """

    _name = 'agrogood.picking.session'
    _description = 'Sesion de preparacion'
    _inherit = ['mail.thread']
    _order = 'date_start desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string="Albaran",
        required=True,
        ondelete='cascade',
        index=True,
    )
    picker_id = fields.Many2one(
        comodel_name='res.users',
        string="Picker",
        required=True,
        tracking=True,
        index=True,
    )
    state = fields.Selection(
        selection=[
            ('assigned', "Asignada"),
            ('in_progress', "En preparacion"),
            ('done', "Terminada"),
            ('cancelled', "Cancelada"),
        ],
        default='assigned',
        required=True,
        tracking=True,
        index=True,
    )

    # --- Tiempos --------------------------------------------------------
    date_assigned = fields.Datetime(
        string="Asignada", default=fields.Datetime.now, readonly=True,
    )
    date_start = fields.Datetime(string="Inicio", readonly=True, tracking=True)
    date_end = fields.Datetime(string="Fin", readonly=True, tracking=True)
    duration_minutes = fields.Float(
        string="Duracion (min)",
        compute='_compute_duration',
        store=True,
        help="Tiempo entre el inicio y el fin de la preparacion.",
    )
    waiting_minutes = fields.Float(
        string="Espera (min)",
        compute='_compute_duration',
        store=True,
        help="Tiempo que estuvo asignada antes de que el Picker la empezara. "
             "Un valor alto indica cuello de botella en el reparto de trabajo, "
             "no lentitud del Picker.",
    )

    # --- Metricas -------------------------------------------------------
    # Todas se calculan desde las lineas del albaran. No se guardan contadores
    # que alguien deba mantener.
    line_count = fields.Integer(compute='_compute_metrics', store=True)
    qty_total = fields.Float(compute='_compute_metrics', store=True,
                             string="Unidades preparadas")
    missing_count = fields.Integer(compute='_compute_metrics', store=True,
                                   string="Faltantes")
    substituted_count = fields.Integer(compute='_compute_metrics', store=True,
                                       string="Sustituidos")
    cancelled_count = fields.Integer(compute='_compute_metrics', store=True,
                                     string="Cancelados")
    not_found_count = fields.Integer(compute='_compute_metrics', store=True,
                                     string="No encontrados")
    incident_count = fields.Integer(compute='_compute_metrics', store=True,
                                    string="Incidencias")
    lines_per_minute = fields.Float(
        string="Lineas por minuto",
        compute='_compute_metrics',
        store=True,
        help="Productividad de la sesion. Solo tiene sentido comparada entre "
             "sesiones parecidas: un pedido de 3 lineas y otro de 40 no se "
             "preparan al mismo ritmo.",
    )

    partner_id = fields.Many2one(related='picking_id.partner_id', store=True,
                                 string="Cliente")
    sale_order_id = fields.Many2one(related='picking_id.sale_id', store=True,
                                    string="Pedido")
    company_id = fields.Many2one(related='picking_id.company_id', store=True)
    note = fields.Text(string="Observaciones del Picker")

    _sql_constraints = [
        ('picking_uniq', 'unique(picking_id)',
         "Este albaran ya tiene una sesion de preparacion."),
    ]

    # ------------------------------------------------------------------
    # Calculos
    # ------------------------------------------------------------------

    @api.depends('picking_id.name', 'picker_id.name')
    def _compute_name(self):
        for s in self:
            s.name = f"{s.picking_id.name} · {s.picker_id.name}" if s.picking_id else ""

    @api.depends('date_assigned', 'date_start', 'date_end')
    def _compute_duration(self):
        for s in self:
            if s.date_start and s.date_end:
                s.duration_minutes = (s.date_end - s.date_start).total_seconds() / 60.0
            else:
                s.duration_minutes = 0.0
            if s.date_assigned and s.date_start:
                s.waiting_minutes = (s.date_start - s.date_assigned).total_seconds() / 60.0
            else:
                s.waiting_minutes = 0.0

    @api.depends('picking_id.move_ids.agrogood_line_status',
                 'picking_id.move_ids.quantity',
                 'picking_id.move_ids.agrogood_incident_note',
                 'duration_minutes')
    def _compute_metrics(self):
        for s in self:
            moves = s.picking_id.move_ids.filtered(lambda m: m.state != 'cancel')
            s.line_count = len(moves)
            s.qty_total = sum(moves.mapped('quantity'))
            s.missing_count = len(moves.filtered(
                lambda m: m.agrogood_line_status == 'missing'))
            s.substituted_count = len(moves.filtered(
                lambda m: m.agrogood_line_status == 'substituted'))
            s.cancelled_count = len(moves.filtered(
                lambda m: m.agrogood_line_status == 'cancelled'))
            s.not_found_count = len(moves.filtered(
                lambda m: m.agrogood_line_status == 'not_found'))
            s.incident_count = len(moves.filtered('agrogood_incident_note'))
            s.lines_per_minute = (
                s.line_count / s.duration_minutes if s.duration_minutes > 0 else 0.0
            )

    # ------------------------------------------------------------------
    # Ciclo de la sesion
    # ------------------------------------------------------------------

    def action_start(self):
        for s in self:
            if s.state != 'assigned':
                raise UserError(_(
                    "La sesion %s ya fue iniciada.", s.display_name))
            s.write({'state': 'in_progress', 'date_start': fields.Datetime.now()})
        return True

    def action_finish(self):
        """Cierra la preparacion. No valida el albaran.

        Son dos actos distintos a proposito: el Picker termina de armar el
        pedido, y el albaran se valida cuando Logistica lo ha controlado. Si
        terminar cerrara el albaran, un error del Picker se convertiria en un
        movimiento de stock irreversible sin que nadie lo revisara.
        """
        for s in self:
            if s.state != 'in_progress':
                raise UserError(_(
                    "La sesion %s no esta en preparacion.", s.display_name))
            sin_revisar = s.picking_id.move_ids.filtered(
                lambda m: m.state != 'cancel' and not m.agrogood_line_status)
            if sin_revisar:
                raise UserError(_(
                    "Faltan lineas por revisar en %(albaran)s:\n%(lineas)s\n\n"
                    "Marca cada producto como confirmado, faltante, sustituido, "
                    "cancelado o no encontrado antes de terminar.",
                    albaran=s.picking_id.name,
                    lineas="\n".join(
                        f"  - {m.product_id.display_name}" for m in sin_revisar),
                ))
            # El control de peso se hace AQUI, no solo al validar el albaran.
            # Detectar un cero de mas cuando Logistica revisa, una hora despues
            # y en la oficina, llega tarde: el Picker ya no tiene la caja
            # delante ni la balanza a mano. El error hay que devolverselo en el
            # momento en que lo comete.
            s.picking_id.move_ids._agrogood_check_weight_tolerance()
            s.write({'state': 'done', 'date_end': fields.Datetime.now()})
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_open_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
        }
