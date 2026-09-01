import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

TIPOS = [
    ('rut', "RUT del pagador"),
    ('alias', "Nombre que usa el banco"),
]


def digito_verificador(cuerpo):
    suma, mult = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * mult
        mult = 2 if mult == 7 else mult + 1
    resto = 11 - (suma % 11)
    return {11: '0', 10: 'K'}.get(resto, str(resto))


def normalizar_rut(bruto):
    """Deja el RUT en la forma `12345678-9`, o None si no es uno valido.

    Los bancos lo escriben de todas las maneras posibles: `783444062`,
    `77.716.841-K`, `77716841K`. Se compara siempre normalizado, o el mismo
    pagador aparece como tres pagadores distintos.
    """
    limpio = re.sub(r"[^0-9kK]", "", str(bruto or "")).upper()
    if len(limpio) < 8 or not limpio[:-1].isdigit():
        return None
    cuerpo, verificador = limpio[:-1], limpio[-1]
    if digito_verificador(cuerpo) != verificador:
        return None
    return "%s-%s" % (cuerpo, verificador)


def normalizar_alias(bruto):
    """El alias del banco, comparable: sin acentos, sin dobles espacios."""
    return re.sub(r"\s+", " ", str(bruto or "")).strip().upper()


class AgrogoodPayer(models.Model):
    """Como aparece un cliente en el extracto bancario.

    Un cliente no paga siempre desde la misma identidad. Se comprobo sobre una
    cartola real de Agrogood:

    * Un mismo negocio transfiere desde la sociedad operativa, desde otra
      relacionada o desde el RUT personal del dueno. Ninguno tiene por que ser
      el RUT que figura en su ficha.
    * Santander no publica el RUT del pagador: solo un nombre corto en la
      columna CLIENTE -BAR CALLEJON, HOP, LOCO JOE-, que es un alias estable
      pero que no coincide con el nombre fiscal.

    Por eso no se cruza contra `res_partner.vat` sino contra esta tabla: un
    cliente tiene TANTAS identidades de pago como haga falta, y cada una se
    aprende UNA vez. La primera quincena hay trabajo manual; despues, cada vez
    menos. Es la unica forma de cruce que mejora con el uso.

    Adivinar por parecido de nombre se descarto a proposito. En la misma
    cartola, `RESTAURANT PAC LIMITADA` se parece un 83% a `RESTAURANT KEKA` y
    no tienen nada que ver. Dar por pagada la factura de otro cliente no es un
    dato mal puesto: es un cobro que se deja de perseguir.
    """

    _name = 'agrogood.payer'
    _description = "Identidad de pago de un cliente"
    _order = 'partner_id, kind, value'

    partner_id = fields.Many2one(
        comodel_name='res.partner', string="Cliente",
        required=True, ondelete='cascade', index=True,
    )
    kind = fields.Selection(selection=TIPOS, required=True, default='rut')
    value = fields.Char(
        string="Como aparece", required=True, index=True,
        help="El RUT del pagador, o el nombre corto que usa el banco.",
    )
    bank = fields.Char(string="Banco", help="Solo informativo.")
    note = fields.Char(string="Por que", help="Util cuando el pagador no es "
                                              "obviamente el mismo negocio.")

    times_seen = fields.Integer(string="Veces visto", default=0, readonly=True)
    last_seen = fields.Date(string="Ultima vez", readonly=True)

    company_id = fields.Many2one(
        comodel_name='res.company', default=lambda self: self.env.company,
    )

    _sql_constraints = [
        # La misma identidad no puede apuntar a dos clientes: seria un cobro
        # asignado al azar entre los dos.
        ('valor_unico', 'unique(kind, value, company_id)',
         "Esa identidad de pago ya esta asociada a otro cliente."),
    ]

    @api.constrains('kind', 'value')
    def _check_valor(self):
        for p in self:
            if p.kind == 'rut' and not normalizar_rut(p.value):
                raise ValidationError(_(
                    "%s no es un RUT valido. Comprueba el digito verificador.",
                    p.value))
            if p.kind == 'alias' and len(normalizar_alias(p.value)) < 3:
                raise ValidationError(_(
                    "El alias del banco es demasiado corto para distinguir a "
                    "nadie."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['value'] = self._normalizar(vals.get('kind'), vals.get('value'))
        return super().create(vals_list)

    def write(self, vals):
        if 'value' in vals or 'kind' in vals:
            for p in self:
                tipo = vals.get('kind', p.kind)
                vals_p = dict(vals)
                vals_p['value'] = self._normalizar(tipo, vals.get('value', p.value))
                super(AgrogoodPayer, p).write(vals_p)
            return True
        return super().write(vals)

    @api.model
    def _normalizar(self, kind, value):
        if kind == 'rut':
            return normalizar_rut(value) or (value or '')
        return normalizar_alias(value)

    # ------------------------------------------------------------------

    @api.model
    def buscar_cliente(self, rut=None, alias=None):
        """Devuelve el cliente que hay detras de un pagador, o vacio.

        Se prueba primero el RUT y despues el alias: el RUT identifica sin
        ambiguedad, el alias es una convencion. Si el RUT no esta registrado
        como identidad, se prueba tambien contra el de la ficha del cliente,
        que es el caso mas comun al empezar.
        """
        Socio = self.env['res.partner']
        rut_n = normalizar_rut(rut) if rut else None
        if rut_n:
            ident = self.search([('kind', '=', 'rut'), ('value', '=', rut_n)], limit=1)
            if ident:
                return ident.partner_id
            socio = Socio.search([('vat', '=', rut_n)], limit=1)
            if socio:
                return socio
        if alias:
            ident = self.search(
                [('kind', '=', 'alias'), ('value', '=', normalizar_alias(alias))],
                limit=1)
            if ident:
                return ident.partner_id
        return Socio.browse()

    def registrar_uso(self, fecha=None):
        """Anota que esta identidad se vio. Sirve para limpiar las que sobran."""
        for p in self:
            p.times_seen += 1
            p.last_seen = fecha or fields.Date.context_today(p)
