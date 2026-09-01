from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    agrogood_session_id = fields.One2many(
        comodel_name='agrogood.picking.session',
        inverse_name='picking_id',
        string="Sesion de preparacion",
    )
    agrogood_picker_id = fields.Many2one(
        comodel_name='res.users',
        string="Picker",
        compute='_compute_agrogood_session_data',
        store=True,
        index='btree_not_null',
    )
    agrogood_session_state = fields.Selection(
        selection=[
            ('assigned', "Asignada"),
            ('in_progress', "En preparacion"),
            ('done', "Terminada"),
            ('cancelled', "Cancelada"),
        ],
        string="Preparacion",
        compute='_compute_agrogood_session_data',
        store=True,
    )
    agrogood_has_variable_weight = fields.Boolean(
        compute='_compute_agrogood_has_variable_weight',
    )

    @api.depends('agrogood_session_id.picker_id', 'agrogood_session_id.state')
    def _compute_agrogood_session_data(self):
        for picking in self:
            sesion = picking.agrogood_session_id[:1]
            picking.agrogood_picker_id = sesion.picker_id
            picking.agrogood_session_state = sesion.state

    @api.depends('move_ids.product_id')
    def _compute_agrogood_has_variable_weight(self):
        for picking in self:
            picking.agrogood_has_variable_weight = any(
                picking.move_ids.mapped('product_id.agrogood_is_variable_weight'))

    # ------------------------------------------------------------------
    # Asignacion a un Picker
    # ------------------------------------------------------------------

    def action_agrogood_assign_picker(self):
        """Abre el asistente para asignar estos albaranes a un Picker."""
        return {
            'type': 'ir.actions.act_window',
            'name': _("Asignar a un Picker"),
            'res_model': 'agrogood.assign.picker',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_ids': self.ids},
        }

    def action_agrogood_open_session(self):
        self.ensure_one()
        if not self.agrogood_session_id:
            raise UserError(_("Este albaran aun no tiene Picker asignado."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'agrogood.picking.session',
            'view_mode': 'form',
            'res_id': self.agrogood_session_id[0].id,
        }

    # ------------------------------------------------------------------
    # Peso variable: sin pedido en espera
    # ------------------------------------------------------------------

    def _agrogood_pickings_without_backorder(self):
        """Albaranes cuyo defecto de cantidad es solo de peso variable.

        Cuando el Picker prepara 19,4 kg de los 20 pedidos, esos 0,6 kg no son
        una entrega pendiente: son lo que peso la caja. Crear un pedido en
        espera dejaria un albaran fantasma abierto por cada linea de peso
        variable, y en pocos dias el listado de entregas pendientes seria
        inservible.

        La condicion es estricta a proposito: basta con que UNA linea corta sea
        de peso fijo para que el albaran vuelva al comportamiento estandar. Si
        faltan 5 unidades de un producto de peso fijo, eso SI es una entrega
        pendiente de verdad.
        """
        resultado = self.browse()
        for picking in self:
            cortas = picking.move_ids.filtered(
                lambda m: m.state != 'cancel' and m._agrogood_is_short())
            if not cortas or not all(
                    m.product_id.agrogood_is_variable_weight for m in cortas):
                continue

            if picking.picking_type_id.code == 'outgoing':
                # En una ENTREGA no hay nada que perseguir: esos 0,6 kg de
                # menos son lo que peso la caja, y se factura lo entregado.
                resultado |= picking
                continue

            # En una COMPRA la falta es mercaderia pagada y no recibida, asi
            # que se aplica la tolerancia de cada producto -la misma que ya usa
            # el Picker en la balanza, para que el equipo no aprenda dos
            # reglas-. Dentro de ella es el peso del envase; por encima, es una
            # entrega corta que hay que reclamarle al proveedor.
            #
            # Sin esta distincion solo caben dos malas opciones: dejar
            # pendientes de 300 gramos que nadie va a reclamar, o cerrar
            # compras a las que les falta mercaderia de verdad.
            if all(m._agrogood_short_within_tolerance() for m in cortas):
                resultado |= picking
        return resultado

    def _check_backorder(self):
        # Se retiran del listado los que no deben generar pedido en espera, de
        # modo que ni siquiera se pregunte por ellos.
        return super()._check_backorder() - self._agrogood_pickings_without_backorder()

    def button_validate(self):
        """Valida comprobando pesos y cerrando sin pedido en espera si procede."""
        self.move_ids._agrogood_check_weight_tolerance()

        sin_espera = self._agrogood_pickings_without_backorder()
        if sin_espera:
            ya = list(self.env.context.get('picking_ids_not_to_backorder') or [])
            self = self.with_context(
                picking_ids_not_to_backorder=ya + sin_espera.ids)
        return super(StockPicking, self).button_validate()
