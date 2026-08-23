from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AgrogoodProductFormat(models.Model):
    """Formato de presentacion de un producto: caja, malla, atado, saco.

    Deliberadamente NO es una unidad de medida. Segun ADR-003, en los productos
    de peso variable la unidad es aquella en la que se factura -el kilogramo- y
    el formato es informativo: le dice al Picker cuantos bultos armar, pero no
    interviene en ningun calculo de stock ni de precio.

    Modelarlo como UoM obligaria a mantener una conversion caja/kg que en fruta
    y verdura no existe: dos cajas de tomate no pesan lo mismo.
    """

    _name = 'agrogood.product.format'
    _description = 'Formato de presentacion'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    reference_weight = fields.Float(
        string="Peso de referencia (kg)",
        digits='Stock Weight',
        help="Peso aproximado del bulto. Solo orientativo, para estimar cuantos "
             "bultos preparar. Nunca se usa para facturar.",
    )
    note = fields.Char(string="Observacion")

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Ya existe un formato con este nombre."),
    ]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    agrogood_is_variable_weight = fields.Boolean(
        string="Peso variable",
        help="El producto se vende y factura por peso real, no por bulto. "
             "El Picker registra el peso preparado y ese es el que se factura.",
    )
    agrogood_format_id = fields.Many2one(
        comodel_name='agrogood.product.format',
        string="Formato de presentacion",
        help="Como se presenta el producto en bodega. Informativo: no interviene "
             "en el calculo de stock ni de precio.",
    )
    agrogood_weight_tolerance = fields.Float(
        string="Tolerancia de peso (%)",
        default=10.0,
        help="Desviacion admitida entre lo pedido y el peso registrado en picking "
             "antes de que el sistema pida confirmacion. Protege contra el error "
             "de tecleo, que en kilos es caro.",
    )

    @api.constrains('agrogood_is_variable_weight', 'uom_id')
    def _check_variable_weight_uom(self):
        """Un producto de peso variable debe medirse en unidades de peso.

        Es la traduccion a codigo de la decision de ADR-003. Sin esta
        restriccion, alguien puede dar de alta un producto de peso variable en
        'Unidades' y el sistema facturara bultos como si fueran kilos, que es
        exactamente el error que la decision pretende evitar.
        """
        categ_peso = self.env.ref('uom.product_uom_categ_kgm', raise_if_not_found=False)
        if not categ_peso:
            return
        for product in self:
            if not product.agrogood_is_variable_weight:
                continue
            if product.uom_id.category_id != categ_peso:
                raise ValidationError(_(
                    "El producto «%(producto)s» esta marcado como de peso variable, "
                    "pero su unidad de medida es «%(unidad)s».\n\n"
                    "Los productos de peso variable se venden y facturan por peso "
                    "real, asi que su unidad debe ser de peso (kg, g, t).\n\n"
                    "Si lo que quieres es indicar que se entrega en cajas o mallas, "
                    "usa el campo «Formato de presentacion», que es informativo.",
                    producto=product.display_name,
                    unidad=product.uom_id.name,
                ))

    @api.constrains('agrogood_weight_tolerance')
    def _check_weight_tolerance(self):
        for product in self:
            if not 0.0 <= product.agrogood_weight_tolerance <= 100.0:
                raise ValidationError(_(
                    "La tolerancia de peso debe estar entre 0 y 100 por ciento."
                ))
