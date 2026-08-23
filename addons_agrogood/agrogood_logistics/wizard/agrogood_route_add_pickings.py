from odoo import _, fields, models
from odoo.exceptions import UserError


class AgrogoodRouteAddPickings(models.TransientModel):
    """Anade albaranes preparados a una ruta.

    Solo ofrece los que estan listos y todavia sin ruta: meter en un camion un
    pedido que aun no se ha preparado es la forma mas rapida de que salga
    incompleto.
    """

    _name = 'agrogood.route.add.pickings'
    _description = 'Anadir albaranes a una ruta'

    route_id = fields.Many2one(
        comodel_name='agrogood.route', string="Ruta", required=True,
    )
    picking_ids = fields.Many2many(
        comodel_name='stock.picking', string="Albaranes",
        domain="[('state', '=', 'assigned'), ('picking_type_code', '=', 'outgoing'),"
               " ('agrogood_route_id', '=', False)]",
        required=True,
    )
    only_prepared = fields.Boolean(
        string="Solo los ya preparados", default=True,
        help="Deja fuera los albaranes cuya preparacion no ha terminado.",
    )

    def action_add(self):
        self.ensure_one()
        pickings = self.picking_ids
        if self.only_prepared:
            sin_preparar = pickings.filtered(
                lambda p: p.agrogood_session_state != 'done')
            if sin_preparar:
                raise UserError(_(
                    "Estos albaranes aun no estan preparados:\n%(lista)s\n\n"
                    "Desmarca 'Solo los ya preparados' si aun asi quieres "
                    "cargarlos.",
                    lista="\n".join(f"  - {p.name}" for p in sin_preparar),
                ))
        ultimo = max(self.route_id.stop_ids.mapped('sequence') or [0])
        self.env['agrogood.route.stop'].create([
            {'route_id': self.route_id.id, 'picking_id': p.id,
             'sequence': ultimo + (i + 1) * 10}
            for i, p in enumerate(pickings)
        ])
        self.route_id.message_post(body=_(
            "Anadidos %(n)s albaranes: %(refs)s",
            n=len(pickings), refs=", ".join(pickings.mapped('name')),
        ))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'agrogood.route',
            'view_mode': 'form',
            'res_id': self.route_id.id,
        }
