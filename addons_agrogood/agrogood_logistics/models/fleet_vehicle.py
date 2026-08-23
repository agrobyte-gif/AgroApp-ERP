from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    agrogood_capacity_kg = fields.Float(
        string="Capacidad de carga (kg)",
        help="Cuanto puede llevar el vehiculo. Se usa para avisar cuando una "
             "ruta se pasa de carga; no impide planificarla, porque quien "
             "reparte sabe si cabe.",
    )
