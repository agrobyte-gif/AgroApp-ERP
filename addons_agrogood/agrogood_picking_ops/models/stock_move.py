from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_is_zero

# Que paso con esta linea al prepararla. Es informacion nueva: el albaran sabe
# cuanto se movio, pero no por que se movio menos de lo pedido.
ESTADO_LINEA = [
    ('confirmed', "Confirmado"),
    ('missing', "Faltante"),
    ('substituted', "Sustituido"),
    ('cancelled', "Cancelado"),
    ('not_found', "No encontrado"),
]


class StockMove(models.Model):
    _inherit = 'stock.move'

    agrogood_line_status = fields.Selection(
        selection=ESTADO_LINEA,
        string="Resultado",
        copy=False,
        index='btree_not_null',
        help="Que ocurrio con este producto al prepararlo.",
    )
    agrogood_substitute_product_id = fields.Many2one(
        comodel_name='product.product',
        string="Sustituido por",
        copy=False,
        help="Producto que se entrego en lugar del pedido.",
    )
    agrogood_incident_note = fields.Char(
        string="Incidencia",
        copy=False,
        help="Que paso exactamente. Lo lee Logistica al controlar el pedido.",
    )
    agrogood_is_variable_weight = fields.Boolean(
        related='product_id.agrogood_is_variable_weight',
        string="Peso variable",
    )
    agrogood_weight_deviation = fields.Float(
        string="Desviacion de peso (%)",
        compute='_compute_agrogood_weight_deviation',
        help="Diferencia porcentual entre lo pedido y lo realmente preparado.",
    )

    @api.depends('product_uom_qty', 'quantity')
    def _compute_agrogood_weight_deviation(self):
        for move in self:
            if float_is_zero(move.product_uom_qty, precision_rounding=0.0001):
                move.agrogood_weight_deviation = 0.0
                continue
            move.agrogood_weight_deviation = (
                (move.quantity - move.product_uom_qty) / move.product_uom_qty * 100.0
            )

    @api.constrains('agrogood_line_status', 'agrogood_substitute_product_id')
    def _check_substitute(self):
        for move in self:
            if move.agrogood_line_status == 'substituted' and \
                    not move.agrogood_substitute_product_id:
                raise ValidationError(_(
                    "Indica por que producto se sustituyo %s.",
                    move.product_id.display_name,
                ))

    def _agrogood_check_weight_tolerance(self):
        """Bloquea desviaciones de peso que superen la tolerancia sin explicar.

        En kilos, un cero de mas es caro: teclear 194 en vez de 19,4 multiplica
        la factura por diez. La tolerancia del producto marca hasta donde una
        diferencia es normal; por encima, se exige que alguien diga que paso.

        No se bloquea sin salida: basta con marcar la linea como faltante,
        sustituida o no encontrada, o dejar una nota de incidencia.
        """
        prec = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        problemas = []
        for move in self:
            if move.state == 'cancel' or not move.product_id.agrogood_is_variable_weight:
                continue
            if float_is_zero(move.product_uom_qty, precision_digits=prec):
                continue
            tolerancia = move.product_id.agrogood_weight_tolerance or 0.0
            if not tolerancia:
                continue
            desviacion = move.agrogood_weight_deviation
            if abs(desviacion) <= tolerancia:
                continue
            # Al RECIBIR una compra, quedarse corto es normal: el proveedor
            # entrego menos, y esa falta se persigue con el pedido en espera,
            # no bloqueando la recepcion. Lo sospechoso al recibir es lo
            # CONTRARIO: registrar mas de lo comprado, que casi siempre es un
            # cero de mas, infla el stock y ensucia el costo promedio.
            #
            # Sin esta distincion Bodega no puede anotar una entrega corta sin
            # pelearse con un mensaje que ademas le habla de marcar la linea
            # como faltante o sustituida: cosas del Picker que no existen en
            # una recepcion.
            if move.picking_id.picking_type_id.code == 'incoming' and desviacion < 0:
                continue
            justificada = (
                move.agrogood_incident_note
                or (move.agrogood_line_status
                    and move.agrogood_line_status != 'confirmed')
            )
            if not justificada:
                problemas.append(move)
        if problemas:
            raise ValidationError(_(
                "Hay pesos que se apartan demasiado de lo pedido:\n\n%(lineas)s\n"
                "%(salida)s",
                salida=_("Se esta registrando MAS de lo comprado. Revisa la "
                         "cantidad; si de verdad llego de mas, deja una nota.")
                if all(m.picking_id.picking_type_id.code == "incoming"
                       for m in problemas)
                else _("Corrige la cantidad, o marca la linea como faltante o "
                       "sustituida, o deja una nota de incidencia."),
                lineas="\n".join(
                    _("  - %(producto)s: se pidieron %(pedido)s y se prepararon "
                      "%(real)s (%(desv)+.1f %%, tolerancia %(tol)s %%)",
                      producto=m.product_id.display_name,
                      pedido=m.product_uom_qty, real=m.quantity,
                      desv=m.agrogood_weight_deviation,
                      tol=m.product_id.agrogood_weight_tolerance)
                    for m in problemas
                ),
            ))
        return True

    def _agrogood_short_within_tolerance(self):
        """True si lo que falta cabe dentro de la tolerancia del producto.

        Se usa al RECIBIR una compra de peso variable. Pedir 20 kg y que lleguen
        19,7 es el peso del envase; que lleguen 15 es una entrega corta. La
        tolerancia es la misma que el Picker tiene en la balanza -por producto,
        10% por defecto- para que no haya dos reglas distintas segun la punta
        del almacen en la que se este.
        """
        self.ensure_one()
        pedido = self.product_uom_qty or 0.0
        if pedido <= 0:
            return True
        falta = pedido - (self.quantity or 0.0)
        margen = pedido * (self.product_id.agrogood_weight_tolerance or 0.0) / 100.0
        return falta <= margen

    def _agrogood_is_short(self):
        """True si se preparo menos de lo pedido."""
        self.ensure_one()
        prec = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        return float_compare(
            self.quantity, self.product_uom_qty, precision_digits=prec) < 0
