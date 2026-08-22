from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AgrogoodPriceVersion(models.Model):
    """Una carga semanal de precios para una linea comercial.

    Existe para que cambiar precios sea un acto revisable: se prepara en
    borrador, se compara contra lo vigente y se publica en bloque. Los precios
    anteriores no se modifican nunca, solo se cierra su vigencia.
    """

    _name = 'agrogood.price.version'
    _description = 'Version de precios'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        required=True,
        default=lambda self: _("Nueva version"),
        tracking=True,
    )
    business_line_id = fields.Many2one(
        comodel_name='agrogood.business.line',
        string="Linea comercial",
        required=True,
        tracking=True,
    )
    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string="Tarifa",
        required=True,
        tracking=True,
        help="Tarifa sobre la que se publican los precios. Se propone la de la "
             "linea comercial y puede cambiarse antes de publicar.",
    )
    date_start = fields.Date(
        string="Vigente desde",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        help="Primer dia en que rigen estos precios, en horario local.",
    )
    state = fields.Selection(
        selection=[
            ('draft', "Borrador"),
            ('applied', "Publicada"),
            ('cancelled', "Cancelada"),
        ],
        default='draft',
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        comodel_name='agrogood.price.version.line',
        inverse_name='version_id',
        string="Precios",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string="Moneda",
    )
    note = fields.Text(string="Observaciones")

    line_count = fields.Integer(compute='_compute_line_count')
    applied_on = fields.Datetime(string="Publicada el", readonly=True, copy=False)
    applied_by_id = fields.Many2one(
        comodel_name='res.users',
        string="Publicada por",
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Calculos
    # ------------------------------------------------------------------

    @api.depends('line_ids')
    def _compute_line_count(self):
        for version in self:
            version.line_count = len(version.line_ids)

    @api.onchange('business_line_id')
    def _onchange_business_line_id(self):
        if self.business_line_id.pricelist_id:
            self.pricelist_id = self.business_line_id.pricelist_id

    # ------------------------------------------------------------------
    # Restricciones
    # ------------------------------------------------------------------

    @api.constrains('line_ids')
    def _check_no_duplicate_products(self):
        for version in self:
            seen = set()
            for line in version.line_ids:
                key = (line.product_tmpl_id.id, line.min_quantity)
                if key in seen:
                    raise ValidationError(_(
                        "El producto %s aparece dos veces con la misma cantidad "
                        "minima. Cada combinacion de producto y cantidad debe ser "
                        "unica dentro de una version.",
                        line.product_tmpl_id.display_name,
                    ))
                seen.add(key)

    # ------------------------------------------------------------------
    # Conversion de fecha
    # ------------------------------------------------------------------

    def _local_start_datetime(self):
        """Devuelve `date_start` a las 00:00 locales, expresado en UTC naive.

        `product.pricelist.item.date_start` es un Datetime almacenado en UTC.
        Convertir la fecha sin tener en cuenta la zona horaria haria que en
        Chile los precios entraran en vigor a las 20:00 o 21:00 del dia
        anterior, que es justo el tipo de error que nadie detecta hasta que un
        pedido sale mal facturado.
        """
        self.ensure_one()
        tz = pytz.timezone(self.env.user.tz or 'America/Santiago')
        local = tz.localize(datetime.combine(self.date_start, time.min))
        return local.astimezone(pytz.UTC).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def action_refresh_comparison(self):
        """Recalcula el precio anterior de cada linea contra la tarifa vigente."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Solo se puede recalcular una version en borrador."))
        self.line_ids._compute_previous_price()
        return True

    def action_apply(self):
        """Publica la version: abre los items nuevos y cierra los anteriores."""
        for version in self:
            if version.state != 'draft':
                raise UserError(_(
                    "La version %s ya no esta en borrador.", version.display_name,
                ))
            if not version.line_ids:
                raise UserError(_(
                    "La version %s no tiene precios que publicar.", version.display_name,
                ))

            start = version._local_start_datetime()
            # date_end es inclusivo en el dominio estandar de Odoo, asi que el
            # item anterior debe cerrarse un segundo antes de que empiece el
            # nuevo. Cerrarlo en el mismo instante dejaria los dos vigentes.
            end_previous = start - timedelta(seconds=1)

            version._close_previous_items(end_previous)
            version._create_pricelist_items(start)

            version.write({
                'state': 'applied',
                'applied_on': fields.Datetime.now(),
                'applied_by_id': self.env.user.id,
            })
            version.message_post(body=_(
                "Version publicada: %(count)s precios vigentes desde %(date)s.",
                count=len(version.line_ids),
                date=fields.Date.to_string(version.date_start),
            ))
        return True

    def action_cancel(self):
        for version in self:
            if version.state == 'applied':
                raise UserError(_(
                    "Una version publicada no se cancela: sus precios ya rigieron y "
                    "deben conservarse. Publica una version nueva que la reemplace."
                ))
            version.state = 'cancelled'
        return True

    def action_reset_to_draft(self):
        for version in self:
            if version.state == 'applied':
                raise UserError(_(
                    "Una version publicada no vuelve a borrador: alterarla cambiaria "
                    "precios que ya estuvieron vigentes."
                ))
            version.state = 'draft'
        return True

    # ------------------------------------------------------------------
    # Publicacion
    # ------------------------------------------------------------------

    def _close_previous_items(self, end_previous):
        """Cierra la vigencia de los items que estos precios reemplazan.

        No se modifica el precio de ningun item existente: solo su `date_end`.
        La diferencia importa, porque el historial debe seguir respondiendo
        que precio estuvo vigente en cada momento.
        """
        self.ensure_one()
        templates = self.line_ids.product_tmpl_id
        if not templates:
            return
        previous = self.env['product.pricelist.item'].search([
            ('pricelist_id', '=', self.pricelist_id.id),
            ('product_tmpl_id', 'in', templates.ids),
            ('applied_on', '=', '1_product'),
            '|', ('date_end', '=', False), ('date_end', '>', end_previous),
        ])
        if previous:
            previous.write({'date_end': end_previous})

    def _create_pricelist_items(self, start):
        self.ensure_one()
        self.env['product.pricelist.item'].create([
            {
                'pricelist_id': self.pricelist_id.id,
                'applied_on': '1_product',
                'product_tmpl_id': line.product_tmpl_id.id,
                'compute_price': 'fixed',
                'fixed_price': line.price,
                'min_quantity': line.min_quantity,
                'date_start': start,
                'company_id': self.company_id.id,
            }
            for line in self.line_ids
        ])

    def action_view_pricelist_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Precios de %s", self.display_name),
            'res_model': 'product.pricelist.item',
            'view_mode': 'list,form',
            'domain': [
                ('pricelist_id', '=', self.pricelist_id.id),
                ('product_tmpl_id', 'in', self.line_ids.product_tmpl_id.ids),
            ],
        }
