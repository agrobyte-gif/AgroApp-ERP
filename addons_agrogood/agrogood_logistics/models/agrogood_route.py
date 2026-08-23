from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AgrogoodRoute(models.Model):
    """El reparto de un conductor en un dia: sus paradas, en orden.

    Odoo sabe que hay albaranes listos para salir, pero no en que camion van,
    con quien, ni en que orden. Esa es la informacion que falta para que el
    reparto deje de organizarse en un papel.
    """

    _name = 'agrogood.route'
    _description = 'Ruta de reparto'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(required=True, copy=False, readonly=True,
                       default=lambda self: _("Nueva"))
    date = fields.Date(
        string="Fecha de reparto", required=True,
        default=fields.Date.context_today, tracking=True, index=True,
    )
    driver_id = fields.Many2one(
        comodel_name='res.users',
        string="Conductor",
        tracking=True,
        index='btree_not_null',
        domain=lambda self: self._driver_domain(),
    )
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle', string="Vehiculo", tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', "Borrador"),
            ('planned', "Planificada"),
            ('in_progress', "En ruta"),
            ('done', "Terminada"),
            ('cancelled', "Cancelada"),
        ],
        default='draft', required=True, tracking=True, index=True,
    )
    stop_ids = fields.One2many(
        comodel_name='agrogood.route.stop', inverse_name='route_id',
        string="Paradas",
    )
    note = fields.Text(string="Instrucciones para el conductor")

    date_start = fields.Datetime(string="Salida", readonly=True, tracking=True)
    date_end = fields.Datetime(string="Regreso", readonly=True, tracking=True)
    duration_hours = fields.Float(string="Duracion (h)", compute='_compute_duration',
                                  store=True)

    # --- Carga y capacidad ---------------------------------------------
    estimated_weight = fields.Float(
        string="Peso estimado (kg)", compute='_compute_load', store=True,
        help="Suma del peso de lo que va en la ruta. En productos de peso "
             "variable es la cantidad misma; en el resto, el peso del producto "
             "por la cantidad.",
    )
    vehicle_capacity = fields.Float(
        related='vehicle_id.agrogood_capacity_kg', string="Capacidad (kg)",
    )
    capacity_usage = fields.Float(
        string="Ocupacion (%)", compute='_compute_load', store=True,
    )
    is_overloaded = fields.Boolean(compute='_compute_load', store=True)

    # --- Metricas -------------------------------------------------------
    stop_count = fields.Integer(compute='_compute_metrics', store=True)
    delivered_count = fields.Integer(compute='_compute_metrics', store=True,
                                     string="Entregadas")
    failed_count = fields.Integer(compute='_compute_metrics', store=True,
                                  string="No entregadas")
    pending_count = fields.Integer(compute='_compute_metrics', store=True,
                                   string="Pendientes")

    company_id = fields.Many2one(
        comodel_name='res.company', required=True,
        default=lambda self: self.env.company,
    )

    # ------------------------------------------------------------------

    def _driver_domain(self):
        grupo = self.env.ref('agrogood_base.group_agrogood_driver',
                             raise_if_not_found=False)
        return [('groups_id', 'in', grupo.ids)] if grupo else []

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for r in self:
            r.duration_hours = (
                (r.date_end - r.date_start).total_seconds() / 3600.0
                if r.date_start and r.date_end else 0.0
            )

    @api.depends('stop_ids.estimated_weight', 'vehicle_id.agrogood_capacity_kg')
    def _compute_load(self):
        for r in self:
            r.estimated_weight = sum(r.stop_ids.mapped('estimated_weight'))
            capacidad = r.vehicle_id.agrogood_capacity_kg or 0.0
            r.capacity_usage = (
                r.estimated_weight / capacidad * 100.0 if capacidad else 0.0
            )
            r.is_overloaded = bool(capacidad and r.estimated_weight > capacidad)

    @api.depends('stop_ids.state')
    def _compute_metrics(self):
        for r in self:
            r.stop_count = len(r.stop_ids)
            r.delivered_count = len(r.stop_ids.filtered(
                lambda s: s.state == 'delivered'))
            r.failed_count = len(r.stop_ids.filtered(
                lambda s: s.state in ('not_delivered', 'rescheduled')))
            r.pending_count = len(r.stop_ids.filtered(
                lambda s: s.state in ('pending', 'on_the_way', 'arrived')))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("Nueva")) == _("Nueva"):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'agrogood.route') or _("Nueva")
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Secuencia de paradas
    # ------------------------------------------------------------------

    def action_sequence_by_window(self):
        """Ordena las paradas por la hora comprometida con cada cliente.

        Es el criterio por defecto y el unico que no necesita saber donde esta
        cada direccion. Sirve mientras no haya optimizador geografico.
        """
        for r in self:
            paradas = r.stop_ids.sorted(
                key=lambda s: (s.scheduled_time or '99:99', s.id))
            for i, s in enumerate(paradas, start=1):
                s.sequence = i * 10
            r.message_post(body=_("Paradas reordenadas por horario comprometido."))
        return True

    def action_optimize_sequence(self):
        """Punto de enganche del optimizador geografico.

        Deliberadamente NO se implementa un optimizador aqui. Calcular rutas
        optimas exige un servicio de mapas externo -Google Routes, Mapbox, OSRM-
        con su coste y su clave, y esa es una decision de negocio que aun no
        esta tomada.

        Lo que si esta hecho es todo lo que ese optimizador necesitaria: las
        paradas ya llevan secuencia, coordenadas y ventana horaria. Conectarlo
        sera escribir el cuerpo de este metodo, no rediseniar el modelo.
        """
        self.ensure_one()
        sin_coordenadas = self.stop_ids.filtered(
            lambda s: not (s.latitude and s.longitude))
        if sin_coordenadas:
            raise UserError(_(
                "Estas paradas no tienen coordenadas, asi que no se pueden "
                "ordenar por distancia:\n%(lista)s\n\n"
                "Completa la ubicacion del cliente o usa el orden por horario.",
                lista="\n".join(
                    f"  - {s.partner_id.display_name}" for s in sin_coordenadas),
            ))
        raise UserError(_(
            "Aun no hay un servicio de mapas configurado.\n\n"
            "El modelo ya guarda coordenadas y ventanas horarias, de modo que "
            "conectar un optimizador (Google Routes, Mapbox u OSRM) es un "
            "desarrollo acotado. Mientras tanto, usa el orden por horario."
        ))

    # ------------------------------------------------------------------
    # Ciclo de la ruta
    # ------------------------------------------------------------------

    def action_plan(self):
        for r in self:
            if not r.stop_ids:
                raise UserError(_("La ruta %s no tiene paradas.", r.name))
            if not r.driver_id:
                raise UserError(_("Asigna un conductor a la ruta %s.", r.name))
            if r.is_overloaded:
                # Aviso, no bloqueo: el jefe de logistica sabe si cabe.
                r.message_post(body=_(
                    "Atencion: la carga estimada (%(peso).0f kg) supera la "
                    "capacidad del vehiculo (%(cap).0f kg).",
                    peso=r.estimated_weight, cap=r.vehicle_capacity,
                ))
            r.state = 'planned'
        return True

    def action_start(self):
        for r in self:
            if r.state != 'planned':
                raise UserError(_("La ruta %s no esta planificada.", r.name))
            r.write({'state': 'in_progress', 'date_start': fields.Datetime.now()})
            r.stop_ids.filtered(lambda s: s.state == 'pending').write(
                {'state': 'on_the_way'})
        return True

    def action_finish(self):
        for r in self:
            abiertas = r.stop_ids.filtered(
                lambda s: s.state in ('pending', 'on_the_way', 'arrived'))
            if abiertas:
                raise UserError(_(
                    "Quedan paradas sin cerrar en %(ruta)s:\n%(lista)s\n\n"
                    "Cada una debe quedar como entregada, no entregada o "
                    "reprogramada.",
                    ruta=r.name,
                    lista="\n".join(
                        f"  - {s.partner_id.display_name}" for s in abiertas),
                ))
            r.write({'state': 'done', 'date_end': fields.Datetime.now()})
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_add_pickings(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Anadir albaranes a la ruta"),
            'res_model': 'agrogood.route.add.pickings',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_route_id': self.id},
        }
