from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Lo que se mira antes de salir. Son seis, y esa es la cifra a proposito: una
# lista de veinte puntos se marca entera sin mirar a los dos dias, y entonces
# deja de servir para lo unico que sirve, que es no salir con algo roto.
#
# El orden no es casual: primero lo que deja el camion tirado en la calle,
# despues lo que arruina la mercaderia. Un conductor que interrumpe la revision
# a la mitad ya ha comprobado lo que mas caro sale.
PUNTOS = [
    ('combustible', "Combustible suficiente para la ruta"),
    ('neumaticos', "Neumaticos y rueda de repuesto"),
    ('luces', "Luces y direccionales"),
    ('frenos', "Frenos"),
    ('frio', "Equipo de frio funcionando"),
    ('carga', "Carga asegurada y puertas cerradas"),
]


class AgrogoodVehicleCheck(models.Model):
    """Revision del vehiculo antes de salir a repartir.

    Viene de un sistema anterior de Agrogood que no llego a usarse, donde
    existia como `VehicleInspection`. Se trae porque el hueco es real y caro:
    un camion que sale con el equipo de frio parado arruina la carga entera, y
    eso no se descubre hasta la primera entrega.

    Se guarda como documento propio y no como una nota en la ruta porque
    interesa la SERIE: el mismo camion fallando en frenos tres veces en un mes
    es informacion que ninguna anotacion suelta da.
    """

    _name = 'agrogood.vehicle.check'
    _description = "Revision del vehiculo antes de salir"
    _order = 'date desc, id desc'
    _inherit = ['mail.thread']

    name = fields.Char(compute='_compute_name', store=True)
    route_id = fields.Many2one(
        comodel_name='agrogood.route', string="Ruta",
        ondelete='cascade', index=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle', string="Vehiculo", required=True, index=True,
    )
    driver_id = fields.Many2one(
        comodel_name='res.users', string="Conductor", required=True,
        default=lambda self: self.env.user, index=True,
    )
    date = fields.Datetime(
        string="Revisado", default=fields.Datetime.now, required=True, index=True,
    )
    odometer = fields.Float(string="Kilometraje")
    note = fields.Text(string="Que se encontro")

    state = fields.Selection(
        selection=[('ok', "Sin novedad"), ('warning', "Con novedad")],
        string="Resultado", compute='_compute_state', store=True, tracking=True,
    )
    problem_count = fields.Integer(compute='_compute_state', store=True)

    company_id = fields.Many2one(
        comodel_name='res.company', default=lambda self: self.env.company,
    )

    # Un campo booleano por punto en lugar de lineas hijas. Con seis puntos
    # fijos, una tabla aparte solo anade una consulta y una pantalla mas para
    # decir lo mismo.
    check_combustible = fields.Boolean(string="Combustible")
    check_neumaticos = fields.Boolean(string="Neumaticos")
    check_luces = fields.Boolean(string="Luces")
    check_frenos = fields.Boolean(string="Frenos")
    check_frio = fields.Boolean(string="Equipo de frio")
    check_carga = fields.Boolean(string="Carga asegurada")

    @api.depends('vehicle_id', 'date')
    def _compute_name(self):
        for r in self:
            fecha = fields.Datetime.context_timestamp(r, r.date) if r.date else False
            r.name = "%s · %s" % (
                r.vehicle_id.name or "?",
                fecha.strftime('%d/%m %H:%M') if fecha else "",
            )

    @api.depends('check_combustible', 'check_neumaticos', 'check_luces',
                 'check_frenos', 'check_frio', 'check_carga')
    def _compute_state(self):
        for r in self:
            malos = sum(1 for clave, _etiqueta in PUNTOS
                        if not r['check_%s' % clave])
            r.problem_count = malos
            r.state = 'ok' if not malos else 'warning'

    def problemas(self):
        """Los puntos que no pasaron, con su texto. Para avisos y pantallas."""
        self.ensure_one()
        return [etiqueta for clave, etiqueta in PUNTOS
                if not self['check_%s' % clave]]

    @api.constrains('note', 'check_combustible', 'check_neumaticos',
                    'check_luces', 'check_frenos', 'check_frio', 'check_carga')
    def _check_explicacion(self):
        """Marcar un fallo obliga a decir cual.

        Sin esto la revision degenera en un boton de 'con novedad' que nadie
        puede accionar: Logistica ve que algo pasa y tiene que llamar al
        conductor para averiguar que, con el camion ya en la calle.
        """
        for r in self:
            if r.problem_count and not (r.note or '').strip():
                raise UserError(_(
                    "Marcaste %(n)s punto(s) sin pasar. Escribe que encontraste "
                    "para que Logistica pueda decidir: %(puntos)s",
                    n=r.problem_count, puntos=", ".join(r.problemas())))

    def _avisar_logistica(self):
        """Deja el aviso en la ruta, que es donde Logistica esta mirando."""
        for r in self.filtered(lambda x: x.state == 'warning' and x.route_id):
            r.route_id.message_post(body=_(
                "Revision del vehiculo con novedad (%(vehiculo)s): "
                "%(puntos)s.<br/>%(nota)s",
                vehiculo=r.vehicle_id.name,
                puntos=", ".join(r.problemas()),
                nota=r.note or "",
            ))

    @api.model_create_multi
    def create(self, vals_list):
        revisiones = super().create(vals_list)
        revisiones._avisar_logistica()
        return revisiones
