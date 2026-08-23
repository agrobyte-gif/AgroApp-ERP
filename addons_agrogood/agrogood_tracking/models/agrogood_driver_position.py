from datetime import timedelta

from odoo import _, api, fields, models


class AgrogoodDriverPosition(models.Model):
    """Una posicion reportada por el telefono de un conductor durante su ruta.

    Se guarda como historico, no como campo unico en la ruta: saber donde esta
    el camion ahora es util, pero reconstruir por donde paso es lo que resuelve
    un reclamo de un cliente que dice que nadie fue.

    El rastreo solo existe mientras la ruta esta en curso. Es una decision
    deliberada, no una limitacion: una herramienta que sigue al trabajador
    fuera de su jornada deja de ser una herramienta.
    """

    _name = 'agrogood.driver.position'
    _description = 'Posicion del conductor'
    _order = 'timestamp desc, id desc'
    _rec_name = 'timestamp'

    route_id = fields.Many2one(
        comodel_name='agrogood.route', string="Ruta",
        required=True, ondelete='cascade', index=True,
    )
    driver_id = fields.Many2one(
        related='route_id.driver_id', string="Conductor", store=True, index=True,
    )
    timestamp = fields.Datetime(
        string="Momento", required=True, default=fields.Datetime.now, index=True,
    )
    latitude = fields.Float(string="Latitud", digits=(10, 7), required=True)
    longitude = fields.Float(string="Longitud", digits=(10, 7), required=True)
    accuracy = fields.Float(
        string="Precision (m)",
        help="Margen de error que reporta el telefono. Por encima de unos 50 m "
             "la posicion es orientativa: en ciudad, entre edificios, el GPS "
             "se degrada bastante.",
    )
    speed = fields.Float(string="Velocidad (km/h)")
    battery = fields.Integer(
        string="Bateria (%)",
        help="Se registra para poder explicar un hueco en el rastro. Un "
             "telefono descargado a media ruta no es un conductor que apago "
             "la app.",
    )
    is_moving = fields.Boolean(string="En movimiento")

    company_id = fields.Many2one(related='route_id.company_id', store=True)

    # ------------------------------------------------------------------

    @api.model
    def _registrar(self, route, vals_list):
        """Guarda un lote de posiciones descartando las inservibles.

        El telefono acumula posiciones cuando pierde cobertura y las envia
        juntas al recuperarla, asi que llegan en lote y desordenadas.

        Se descartan dos cosas: las de precision muy mala, que ensucian el
        rastro con saltos de cientos de metros, y las repetidas, porque un
        camion detenido reporta la misma posicion cada minuto y en una jornada
        genera miles de registros identicos.
        """
        limpias = []
        ultima = self.search([('route_id', '=', route.id)], limit=1)
        for v in vals_list:
            if not v.get('latitude') or not v.get('longitude'):
                continue
            if (v.get('accuracy') or 0) > 200:
                continue
            if ultima and self._misma_posicion(ultima, v):
                continue
            limpias.append(dict(v, route_id=route.id))
        return self.create(limpias) if limpias else self.browse()

    @api.model
    def _misma_posicion(self, anterior, vals, umbral=0.00015):
        """True si la posicion no se ha movido lo suficiente como para guardarla.

        0,00015 grados son unos 15 metros, por debajo de la precision tipica
        de un GPS urbano.
        """
        return (abs(anterior.latitude - vals['latitude']) < umbral
                and abs(anterior.longitude - vals['longitude']) < umbral)

    @api.model
    def _cron_purgar(self):
        """Borra el rastro de rutas cerradas hace mas de 60 dias.

        Dos motivos. Uno tecnico: una ruta genera cientos de posiciones al dia
        y la tabla crece sin freno. Otro de fondo: guardar indefinidamente el
        recorrido de una persona no tiene justificacion operativa una vez
        pasado el plazo en que un cliente puede reclamar una entrega.
        """
        limite = fields.Datetime.now() - timedelta(days=60)
        viejas = self.search([
            ('timestamp', '<', limite),
            ('route_id.state', 'in', ('done', 'cancelled')),
        ])
        n = len(viejas)
        viejas.unlink()
        return n
