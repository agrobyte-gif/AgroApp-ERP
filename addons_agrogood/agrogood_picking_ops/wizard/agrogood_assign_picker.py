from odoo import _, fields, models
from odoo.exceptions import UserError


class AgrogoodAssignPicker(models.TransientModel):
    """Asigna varios albaranes a un Picker de una vez.

    Felipe reparte el trabajo del dia en bloque, no albaran por albaran. Por
    eso el asistente acepta una seleccion y muestra la carga actual de cada
    Picker antes de decidir.
    """

    _name = 'agrogood.assign.picker'
    _description = 'Asignar albaranes a un Picker'

    picking_ids = fields.Many2many(
        comodel_name='stock.picking', string="Albaranes", required=True,
    )
    picker_id = fields.Many2one(
        comodel_name='res.users', string="Picker", required=True,
        domain=lambda self: self._picker_domain(),
    )
    current_load = fields.Integer(
        string="Sesiones abiertas de este Picker",
        compute='_compute_current_load',
    )

    def _picker_domain(self):
        grupo = self.env.ref('agrogood_base.group_agrogood_picker',
                             raise_if_not_found=False)
        return [('groups_id', 'in', grupo.ids)] if grupo else []

    def _compute_current_load(self):
        Sesion = self.env['agrogood.picking.session']
        for w in self:
            w.current_load = Sesion.search_count([
                ('picker_id', '=', w.picker_id.id),
                ('state', 'in', ('assigned', 'in_progress')),
            ]) if w.picker_id else 0

    def action_assign(self):
        self.ensure_one()
        Sesion = self.env['agrogood.picking.session']
        ya_asignados = self.picking_ids.filtered('agrogood_session_id')
        if ya_asignados:
            raise UserError(_(
                "Estos albaranes ya tienen Picker asignado: %s",
                ", ".join(ya_asignados.mapped('name')),
            ))
        sesiones = Sesion.create([
            {'picking_id': p.id, 'picker_id': self.picker_id.id}
            for p in self.picking_ids
        ])
        for s in sesiones:
            s.picking_id.message_post(body=_(
                "Preparacion asignada a %s.", self.picker_id.name))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Sesiones creadas"),
            'res_model': 'agrogood.picking.session',
            'view_mode': 'list,form',
            'domain': [('id', 'in', sesiones.ids)],
        }
