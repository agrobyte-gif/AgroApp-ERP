from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_is_zero


class AgrogoodPriceVersionLine(models.Model):
    """El precio propuesto para un producto dentro de una version."""

    _name = 'agrogood.price.version.line'
    _description = 'Precio de una version'
    _order = 'product_tmpl_id, min_quantity'

    version_id = fields.Many2one(
        comodel_name='agrogood.price.version',
        string="Version",
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_tmpl_id = fields.Many2one(
        comodel_name='product.template',
        string="Producto",
        required=True,
        domain=[('sale_ok', '=', True)],
    )
    uom_name = fields.Char(
        related='product_tmpl_id.uom_id.name',
        string="Unidad",
    )
    min_quantity = fields.Float(
        string="Cantidad minima",
        default=0.0,
        digits='Product Unit of Measure',
        help="Cantidad a partir de la cual se aplica este precio. Cero significa "
             "que aplica a cualquier cantidad.",
    )
    price = fields.Monetary(
        string="Precio nuevo",
        required=True,
        currency_field='currency_id',
    )
    previous_price = fields.Monetary(
        string="Precio anterior",
        compute='_compute_previous_price',
        store=True,
        currency_field='currency_id',
        help="Precio vigente en la tarifa al momento de preparar esta version.",
    )
    variation = fields.Float(
        string="Variacion",
        compute='_compute_variation',
        store=True,
        digits=(16, 4),
        help="Diferencia respecto del precio anterior, como fraccion: 0,05 es un "
             "aumento del 5 %. Se guarda asi porque el widget 'percentage' de Odoo "
             "multiplica por 100 al mostrar.",
    )
    trend = fields.Selection(
        selection=[
            ('up', "Sube"),
            ('down', "Baja"),
            ('flat', "Sin cambio"),
            ('new', "Nuevo"),
        ],
        compute='_compute_variation',
        store=True,
    )

    currency_id = fields.Many2one(related='version_id.currency_id')
    state = fields.Selection(related='version_id.state', store=True)

    # ------------------------------------------------------------------
    # Comparacion con lo vigente
    # ------------------------------------------------------------------

    @api.depends('product_tmpl_id', 'min_quantity',
                 'version_id.pricelist_id', 'version_id.date_start')
    def _compute_previous_price(self):
        """Precio vigente justo antes de que arranque esta version.

        La consulta se hace explicitamente a un segundo antes de `date_start`,
        no en el momento actual. Consultar "ahora" da una comparacion
        equivocada en dos situaciones habituales:

        * La version se prepara para la semana que viene, cuando lo que
          interesa es contra que precio va a competir el dia que entre.
        * La version anterior ya esta publicada pero aun no vigente. Preguntar
          "ahora" la ignora y devuelve el precio de lista del producto, con lo
          que la variacion sale inflada.

        Se almacena y no se recalcula despues de publicar: sus dependencias
        (producto, tarifa y fecha) ya no cambian, de modo que la comparacion
        queda congelada tal como se reviso.
        """
        for line in self:
            version = line.version_id
            pricelist = version.pricelist_id
            if not pricelist or not line.product_tmpl_id or not version.date_start:
                line.previous_price = 0.0
                continue
            momento = version._local_start_datetime() - timedelta(seconds=1)
            line.previous_price = pricelist._get_product_price(
                line.product_tmpl_id,
                line.min_quantity or 1.0,
                date=momento,
            )

    @api.depends('price', 'previous_price')
    def _compute_variation(self):
        for line in self:
            rounding = line.currency_id.rounding or 0.01
            if float_is_zero(line.previous_price, precision_rounding=rounding):
                line.variation = 0.0
                line.trend = 'new'
                continue
            line.variation = (line.price - line.previous_price) / line.previous_price
            comparison = float_compare(
                line.price, line.previous_price, precision_rounding=rounding,
            )
            line.trend = 'up' if comparison > 0 else 'down' if comparison < 0 else 'flat'

    # ------------------------------------------------------------------
    # Restricciones
    # ------------------------------------------------------------------

    @api.constrains('price')
    def _check_price(self):
        for line in self:
            if line.price < 0:
                raise ValidationError(_(
                    "El precio de %s no puede ser negativo.",
                    line.product_tmpl_id.display_name,
                ))

    @api.constrains('min_quantity')
    def _check_min_quantity(self):
        for line in self:
            if line.min_quantity < 0:
                raise ValidationError(_("La cantidad minima no puede ser negativa."))
