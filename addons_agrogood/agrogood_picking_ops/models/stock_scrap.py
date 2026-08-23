from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Por que se perdio la mercaderia. Odoo registra CUANTO se perdio, pero no por
# que, y sin eso el control de mermas no sirve para decidir nada: no distingue
# entre un problema de proveedor, uno de camara de frio y uno de rotacion.
MOTIVOS_MERMA = [
    ('expired', "Vencido"),
    ('damaged', "Danado en bodega"),
    ('damaged_transport', "Danado en transporte"),
    ('quality', "Calidad insuficiente"),
    ('supplier', "Llego mal del proveedor"),
    ('customer_refused', "Rechazado por el cliente"),
    ('inventory_diff', "Diferencia de inventario"),
    ('other', "Otro"),
]

# Motivos cuya causa esta fuera de Agrogood: sirven para reclamar.
RECLAMABLES = ('supplier', 'damaged_transport')


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    agrogood_reason = fields.Selection(
        selection=MOTIVOS_MERMA,
        string="Motivo de la merma",
        required=True,
        default='damaged',
        tracking=True,
    )
    agrogood_reason_note = fields.Char(string="Detalle")
    agrogood_claimable = fields.Boolean(
        string="Reclamable",
        compute='_compute_agrogood_claimable',
        store=True,
        help="La causa esta fuera de Agrogood, asi que la perdida puede "
             "reclamarse al proveedor o al transportista.",
    )
    agrogood_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="A quien se reclama",
        help="Proveedor o transportista responsable de la perdida.",
    )
    agrogood_cost = fields.Monetary(
        string="Costo de la perdida",
        compute='_compute_agrogood_cost',
        store=True,
        currency_field='agrogood_currency_id',
        help="Lo que costo la mercaderia perdida, para poder sumar cuanto se "
             "pierde al mes y por que motivo.",
    )
    agrogood_currency_id = fields.Many2one(
        related='company_id.currency_id', string="Moneda",
    )

    @api.depends('agrogood_reason')
    def _compute_agrogood_claimable(self):
        for s in self:
            s.agrogood_claimable = s.agrogood_reason in RECLAMABLES

    @api.depends('scrap_qty', 'product_id')
    def _compute_agrogood_cost(self):
        for s in self:
            s.agrogood_cost = s.scrap_qty * (s.product_id.standard_price or 0.0)

    @api.constrains('agrogood_reason', 'agrogood_partner_id')
    def _check_claimable_partner(self):
        for s in self:
            if s.agrogood_claimable and not s.agrogood_partner_id:
                raise ValidationError(_(
                    "Esta merma es reclamable (%(motivo)s), asi que hay que "
                    "indicar a quien se le reclama. Sin ese dato la perdida se "
                    "asume sin poder recuperarla.",
                    motivo=dict(MOTIVOS_MERMA)[s.agrogood_reason],
                ))
