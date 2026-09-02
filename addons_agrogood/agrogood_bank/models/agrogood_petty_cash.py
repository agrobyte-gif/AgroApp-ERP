from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

TIPOS = [
    ('gasto', "Gasto"),
    ('reposicion', "Reposicion del sobre"),
]

# Las categorias son las que aparecen de verdad en el dia a dia de Agrogood.
# Deliberadamente cortas: una lista de veinte hace que todos elijan "Otros",
# y entonces la lista no sirve para nada.
CATEGORIAS = [
    ('combustible', "Combustible"),
    ('peaje', "Peajes y estacionamiento"),
    ('flete', "Fletes y acarreos"),
    ('insumos', "Insumos de bodega"),
    ('mercaderia', "Mercaderia de urgencia"),
    ('mantencion', "Mantencion y reparaciones"),
    ('otros', "Otros"),
]


class AgrogoodPettyCash(models.Model):
    """El sobre de la caja chica: lo que sale, lo que entra y lo que queda.

    NO genera asientos contables, igual que la cobranza no asienta pagos. Un
    apunte contable exige permisos de contabilidad, y quien saca plata del
    sobre para un peaje es un conductor. Esto registra el movimiento con su
    boleta; cuadrarlo con la contabilidad es trabajo mensual de Direccion, y
    para eso estan la lista y el saldo.

    Dos controles, que son todo el sentido de una caja chica:

    1. **Un gasto exige boleta**, y si no la hay, exige decir por que no. Sin
       eso, "se gastaron 20 mil en algo" es indistinguible de que falten 20 mil.
    2. **Quien gasta no repone.** La reposicion del sobre la hace Direccion.
       Si la misma persona pudiera sacar y rellenar, el saldo dejaria de
       significar nada: siempre cuadraria.
    """

    _name = 'agrogood.petty.cash'
    _description = "Movimiento de caja chica"
    _order = 'date desc, id desc'
    _inherit = ['mail.thread']

    name = fields.Char(compute='_compute_name', store=True)
    date = fields.Date(string="Fecha", required=True, index=True,
                       default=fields.Date.context_today)
    kind = fields.Selection(selection=TIPOS, string="Tipo", required=True,
                            default='gasto', index=True)
    amount = fields.Monetary(string="Monto", required=True)
    currency_id = fields.Many2one(
        comodel_name='res.currency', default=lambda self: self.env.company.currency_id,
    )
    category = fields.Selection(selection=CATEGORIAS, string="En que")
    note = fields.Char(string="Detalle", help="En que se gasto, con palabras.")
    user_id = fields.Many2one(
        comodel_name='res.users', string="Quien", required=True, index=True,
        default=lambda self: self.env.user, readonly=True,
    )
    receipt = fields.Image(string="Boleta", max_width=1280, max_height=1280,
                           attachment=True)
    no_receipt_reason = fields.Char(
        string="Por que no hay boleta",
        help="Solo cuando de verdad no la dieron. Queda a la vista.",
    )
    balance_after = fields.Monetary(
        string="Queda en el sobre", compute='_compute_balance_after',
        help="Lo que quedaba en el sobre despues de este movimiento.",
    )
    company_id = fields.Many2one(
        comodel_name='res.company', default=lambda self: self.env.company,
    )

    @api.depends('kind', 'date', 'amount', 'category')
    def _compute_name(self):
        tipos = dict(TIPOS)
        cats = dict(CATEGORIAS)
        for m in self:
            que = cats.get(m.category) or tipos.get(m.kind, '')
            m.name = "%s %s %s" % (
                m.date or '', que,
                "{:,.0f}".format(m.amount or 0).replace(",", "."))

    def _compute_balance_after(self):
        """Lo que quedaba en el sobre justo despues de cada movimiento.

        Se calcula recorriendo desde el principio y no restando del total: asi
        un movimiento antiguo que se corrige arrastra el saldo de todos los
        posteriores, que es lo que hace que la lista se pueda auditar de arriba
        abajo sin tener que rehacer las cuentas a mano.
        """
        todos = self.search([], order='date asc, id asc')
        acumulado = 0.0
        saldos = {}
        for m in todos:
            acumulado += m.amount if m.kind == 'reposicion' else -m.amount
            saldos[m.id] = acumulado
        for m in self:
            m.balance_after = saldos.get(m.id, 0.0)

    @api.constrains('amount')
    def _check_monto(self):
        for m in self:
            if m.amount <= 0:
                raise ValidationError(_(
                    "El monto tiene que ser mayor que cero. Una reposicion y "
                    "un gasto se distinguen por el tipo, no por el signo."))

    @api.constrains('kind', 'receipt', 'no_receipt_reason', 'category')
    def _check_respaldo(self):
        for m in self:
            if m.kind != 'gasto':
                continue
            if not m.category:
                raise ValidationError(_("Di en que se gasto."))
            if not m.receipt and not (m.no_receipt_reason or '').strip():
                raise ValidationError(_(
                    "Falta la boleta. Si de verdad no la dieron, escribe por "
                    "que: sin eso, un gasto sin respaldo no se distingue de "
                    "una plata que falta."))

    @api.model
    def saldo(self):
        """Lo que hay ahora mismo en el sobre."""
        movimientos = self.search([])
        return sum(m.amount if m.kind == 'reposicion' else -m.amount
                   for m in movimientos)

    @api.model
    def gastado_en_el_mes(self):
        primero = fields.Date.context_today(self).replace(day=1)
        return sum(self.search([('kind', '=', 'gasto'),
                                ('date', '>=', primero)]).mapped('amount'))

    @api.model_create_multi
    def create(self, vals_list):
        movimientos = super().create(vals_list)
        for m in movimientos:
            # El movimiento queda en su propia conversacion con quien lo hizo y
            # cuanto quedaba. Es lo que permite reconstruir despues por que el
            # sobre no cuadra, sin depender de que nadie se acuerde.
            m.message_post(body=_(
                "%(quien)s registro %(tipo)s de %(monto)s. Quedan %(saldo)s "
                "en el sobre.",
                quien=m.user_id.name,
                tipo=dict(TIPOS).get(m.kind, '').lower(),
                monto="{:,.0f}".format(m.amount).replace(",", "."),
                saldo="{:,.0f}".format(m.balance_after).replace(",", ".")))
        return movimientos

    def action_agrogood_ver_boleta(self):
        self.ensure_one()
        if not self.receipt:
            raise UserError(_("Este movimiento no tiene boleta: %s",
                              self.no_receipt_reason or _("sin explicacion")))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/image/agrogood.petty.cash/%s/receipt' % self.id,
            'target': 'new',
        }
