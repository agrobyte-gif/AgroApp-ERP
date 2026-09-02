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
    `77.716.841-K`, `77716841K`, y Santander ademas lo rellena de ceros por la
    izquierda hasta once digitos -`00763341712`-. Se compara siempre
    normalizado, o el mismo pagador aparece como cuatro pagadores distintos.
    """
    limpio = re.sub(r"[^0-9kK]", "", str(bruto or "")).upper().lstrip("0")
    if len(limpio) < 8 or len(limpio) > 9 or not limpio[:-1].isdigit():
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

    Y al reves tampoco es uno a uno: **un mismo RUT paga por varios clientes**.
    En esa cartola, 108 de 523 RUT liquidaron facturas de mas de un negocio.
    Por eso existe `is_shared`: una identidad que se demuestra compartida deja
    de asignar sola. Se prefirio aprenderlo a suponerlo -marcar de entrada como
    dudoso todo RUT repetido dejaba casi la mitad de los abonos esperando a una
    persona, que es tanto trabajo manual como no tener el modulo-.
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

    is_shared = fields.Boolean(
        string="Lo usan varios clientes", default=False,
        help="Ese RUT o ese nombre paga facturas de mas de un cliente, de modo "
             "que por si solo no decide de quien es el abono. Deja de asignar "
             "automaticamente y pasa a esperar a una persona.",
    )

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
    def resolver(self, rut=None, alias=None):
        """Quien pago, y de donde se dedujo. Devuelve (cliente, motivo).

        `motivo` es uno de: `rut_aprendido`, `rut_ficha`, `alias_aprendido`,
        `compartida`, `discrepan`, `nada`. Importa tanto como el cliente: en la
        pantalla de conciliacion decide si el abono se da por resuelto o espera
        a una persona, y sin el habria que volver a deducirlo para explicarlo.

        Se miran las DOS senales en lugar de quedarse con la primera que
        acierta. Si el RUT dice un cliente y el nombre dice otro, eso no es un
        empate que se rompa por orden de preferencia: es justo el caso en que
        equivocarse sale caro, y lo unico correcto es no decidirlo solo.
        """
        Socio = self.env['res.partner']
        vacio = Socio.browse()
        rut_n = normalizar_rut(rut) if rut else None
        alias_n = normalizar_alias(alias) if alias else None

        compartida = False

        por_rut, motivo_rut = vacio, None
        if rut_n:
            ident = self.search([('kind', '=', 'rut'), ('value', '=', rut_n)], limit=1)
            if ident and ident.is_shared:
                compartida = True
            elif ident:
                por_rut, motivo_rut = ident.partner_id, 'rut_aprendido'
            else:
                socio = Socio.search([('vat', '=', rut_n)], limit=1)
                if socio:
                    por_rut, motivo_rut = socio, 'rut_ficha'

        por_alias = vacio
        if alias_n:
            ident = self.search(
                [('kind', '=', 'alias'), ('value', '=', alias_n)], limit=1)
            if ident and ident.is_shared:
                compartida = True
            elif ident:
                por_alias = ident.partner_id

        if por_rut and por_alias and por_rut != por_alias:
            return vacio, 'discrepan'
        # Una senal compartida no descarta la otra: si el RUT lo usan dos
        # clientes pero el banco trae ademas el nombre corto de uno de ellos,
        # eso resuelve el abono. Para eso esta el alias. Solo cuando no queda
        # ninguna senal util se devuelve el abono a una persona.
        if por_rut:
            return por_rut, motivo_rut
        if por_alias:
            return por_alias, 'alias_aprendido'
        if compartida:
            return vacio, 'compartida'
        return vacio, 'nada'

    @api.model
    def buscar_cliente(self, rut=None, alias=None):
        """El cliente que hay detras de un pagador, o vacio."""
        return self.resolver(rut=rut, alias=alias)[0]

    @api.model
    def aprender(self, partner, rut=None, alias=None, bank=None):
        """Guarda como paga este cliente. Devuelve las identidades tocadas.

        Se aprende SOLO cuando una persona enlaza el abono a mano. Nunca a
        partir de un cruce automatico: aprender de lo que uno mismo dedujo
        convierte un error en una regla, y a partir de ahi se repite solo.

        Si el valor ya esta a nombre de otro cliente no se pisa ni se duplica:
        se marca la identidad existente como COMPARTIDA. Eso es lo que pasa de
        verdad -en una cartola real, 108 de 523 RUT pagaron facturas de mas de
        un negocio: la sociedad que paga por dos locales, el dueno que paga por
        el suyo y por el de un socio-. A partir de ese momento ese RUT deja de
        asignar solo y los abonos que lleguen con el esperan a una persona, que
        es lo unico honesto cuando el dato no alcanza para decidir.
        """
        tocadas = self.browse()
        for tipo, bruto in (('rut', rut), ('alias', alias)):
            if not bruto:
                continue
            valor = self._normalizar(tipo, bruto)
            if tipo == 'rut' and not normalizar_rut(valor):
                continue
            if tipo == 'alias' and len(valor) < 3:
                continue
            existente = self.search([('kind', '=', tipo), ('value', '=', valor)], limit=1)
            if existente and existente.partner_id == partner:
                tocadas |= existente
                continue
            if existente:
                existente.is_shared = True
                existente.note = (existente.note or "") or _(
                    "Lo usan varios clientes; el abono se asigna a mano.")
                tocadas |= existente
                continue
            tocadas |= self.create({
                'partner_id': partner.id, 'kind': tipo,
                'value': valor, 'bank': bank or False,
            })
        return tocadas

    def registrar_uso(self, fecha=None):
        """Anota que esta identidad se vio. Sirve para limpiar las que sobran."""
        for p in self:
            p.times_seen += 1
            p.last_seen = fecha or fields.Date.context_today(p)
