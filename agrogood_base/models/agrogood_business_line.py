from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AgrogoodBusinessLine(models.Model):
    """Linea comercial con la que Agrogood segmenta a sus clientes.

    Es el eje sobre el que se resuelven precios y condiciones comerciales:
    cliente -> linea comercial -> tarifa -> item vigente -> precio.
    Se modela como dato maestro y no como seleccion fija para que Ventas pueda
    crear lineas nuevas sin intervencion tecnica.
    """

    _name = 'agrogood.business.line'
    _description = 'Linea comercial'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help="Codigo corto usado en informes y cargas masivas. Por ejemplo HORECA.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string="Color")

    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string="Tarifa por defecto",
        help="Tarifa que se propone al asignar esta linea comercial a un cliente. "
             "No se aplica de forma retroactiva a clientes ya existentes.",
    )
    payment_term_id = fields.Many2one(
        comodel_name='account.payment.term',
        string="Condicion de pago por defecto",
    )
    note = fields.Text(string="Condiciones comerciales")

    partner_ids = fields.One2many(
        comodel_name='res.partner',
        inverse_name='agrogood_business_line_id',
        string="Clientes",
    )
    partner_count = fields.Integer(
        string="Numero de clientes",
        compute='_compute_partner_count',
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', "Ya existe otra linea comercial con este codigo."),
    ]

    @api.depends('partner_ids')
    def _compute_partner_count(self):
        counts = dict(self.env['res.partner']._read_group(
            domain=[('agrogood_business_line_id', 'in', self.ids)],
            groupby=['agrogood_business_line_id'],
            aggregates=['__count'],
        ))
        for line in self:
            line.partner_count = counts.get(line, 0)

    @api.constrains('code')
    def _check_code(self):
        for line in self:
            if not line.code.strip():
                raise ValidationError(_("El codigo de la linea comercial no puede estar vacio."))

    def action_view_partners(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Clientes de %s", self.name),
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('agrogood_business_line_id', '=', self.id)],
            'context': {'default_agrogood_business_line_id': self.id},
        }
