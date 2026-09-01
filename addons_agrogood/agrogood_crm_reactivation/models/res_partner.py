from datetime import timedelta

import pytz

from odoo import api, fields, models

DIAS = [('0', "Lunes"), ('1', "Martes"), ('2', "Miercoles"), ('3', "Jueves"),
        ('4', "Viernes"), ('5', "Sabado"), ('6', "Domingo")]


def _fecha_local(momento, tz):
    """Fecha del calendario en que ocurrio `momento` para quien vive en `tz`.

    Odoo almacena los Datetime en UTC. Un pedido de las 21:30 del martes en
    Concepcion esta guardado como las 01:30 del miercoles, y `.date()` diria
    miercoles. Para el cliente, y para Ventas, fue el martes.
    """
    return pytz.utc.localize(momento).astimezone(tz).date()


class ResPartner(models.Model):
    """Comportamiento de compra del cliente, calculado desde las ventas reales.

    Las metricas viven aqui y no en un modelo aparte porque son atributos del
    cliente, no entidades propias. Un modelo paralelo obligaria a mantenerlo en
    sincronia con las ventas y a duplicar el enlace en cada consulta.

    Se almacenan y las recalcula un proceso nocturno. Calcularlas al vuelo
    obligaria a recorrer el historico de pedidos cada vez que alguien abre una
    ficha, y con 158 clientes eso ya se nota.
    """

    _inherit = 'res.partner'

    agrogood_payer_ids = fields.One2many(
        comodel_name='agrogood.payer', inverse_name='partner_id',
        string="Como paga",
        help="Los RUT y nombres cortos desde los que este cliente "
             "transfiere. Un negocio no paga siempre desde el mismo.",
    )
    agrogood_order_count = fields.Integer(string="Pedidos", readonly=True)
    agrogood_first_order_date = fields.Date(string="Primera compra", readonly=True)
    agrogood_last_order_date = fields.Date(string="Ultima compra", readonly=True)
    agrogood_days_since_order = fields.Integer(
        string="Dias sin comprar",
        compute='_compute_agrogood_days_since_order',
        search='_search_agrogood_days_since_order',
        help="Se calcula al vuelo: almacenarlo obligaria a recalcular los 158 "
             "clientes cada medianoche solo porque cambio la fecha.",
    )
    agrogood_avg_ticket = fields.Monetary(
        string="Ticket medio", readonly=True, currency_field='currency_id',
    )
    agrogood_total_purchased = fields.Monetary(
        string="Total comprado", readonly=True, currency_field='currency_id',
    )
    agrogood_avg_days_between = fields.Float(
        string="Cada cuantos dias compra", readonly=True,
        help="Promedio de dias entre pedidos. Es la referencia para saber si un "
             "cliente se esta retrasando.",
    )
    agrogood_usual_weekday = fields.Selection(
        selection=DIAS, string="Dia habitual", readonly=True,
        help="El dia de la semana en que mas veces ha pedido.",
    )
    agrogood_volume_trend = fields.Float(
        string="Tendencia (%)", readonly=True,
        help="Variacion de lo comprado en los ultimos 60 dias frente a los 60 "
             "anteriores. Negativo significa que esta comprando menos.",
    )
    agrogood_customer_status = fields.Selection(
        selection=[
            ('new', "Nuevo"),
            ('active', "Activo"),
            ('at_risk', "En riesgo"),
            ('inactive', "Inactivo"),
            ('lost', "Perdido"),
        ],
        string="Situacion comercial", readonly=True, index='btree_not_null',
        help="Se deduce del retraso frente a su propia frecuencia, no de un "
             "numero fijo de dias: un cliente que compra cada quince dias no "
             "esta en riesgo por llevar diez sin pedir.",
    )
    agrogood_top_products = fields.Char(
        string="Compra habitualmente", readonly=True,
    )

    # ------------------------------------------------------------------

    def _compute_agrogood_days_since_order(self):
        hoy = fields.Date.context_today(self)
        for p in self:
            p.agrogood_days_since_order = (
                (hoy - p.agrogood_last_order_date).days
                if p.agrogood_last_order_date else 0
            )

    def _search_agrogood_days_since_order(self, operator, value):
        hoy = fields.Date.context_today(self)
        limite = hoy - timedelta(days=int(value))
        # Mas dias sin comprar equivale a una fecha de ultima compra mas
        # antigua, asi que el operador se invierte.
        inverso = {'>': '<', '>=': '<=', '<': '>', '<=': '>=',
                   '=': '=', '!=': '!='}
        return [('agrogood_last_order_date', inverso.get(operator, operator), limite)]

    # ------------------------------------------------------------------
    # Recalculo
    # ------------------------------------------------------------------

    def _agrogood_recompute_metrics(self):
        """Recalcula el comportamiento de compra desde los pedidos confirmados.

        Se agrupa por cliente comercial: los locales de un mismo RUT son un
        solo cliente a efectos de seguimiento. Perseguir por separado a BUFALO
        BEEF y a BURGER BAR, que son el mismo dueno, seria llamarlo dos veces.
        """
        socios = self or self.search([('agrogood_business_line_id', '!=', False)])
        Pedido = self.env['sale.order']
        hoy = fields.Date.context_today(self)
        # El recalculo lo dispara un cron, y el usuario del cron puede no tener
        # zona horaria. Se cae a la de Agrogood en lugar de a UTC, que es el
        # valor que produciria el error que esta conversion evita.
        tz = pytz.timezone(self.env.user.tz or 'America/Santiago')

        for socio in socios:
            comercial = socio.commercial_partner_id
            pedidos = Pedido.search([
                ('partner_id', 'child_of', comercial.id),
                ('state', 'in', ('sale', 'done')),
            ], order='date_order')
            if not pedidos:
                socio.write({
                    'agrogood_order_count': 0,
                    'agrogood_customer_status': 'new',
                    'agrogood_first_order_date': False,
                    'agrogood_last_order_date': False,
                    'agrogood_avg_ticket': 0.0,
                    'agrogood_total_purchased': 0.0,
                    'agrogood_avg_days_between': 0.0,
                    'agrogood_usual_weekday': False,
                    'agrogood_volume_trend': 0.0,
                    'agrogood_top_products': False,
                })
                continue

            # `date_order` es un Datetime que Odoo guarda en UTC, y `hoy` es la
            # fecha LOCAL. Tomar `.date()` sin convertir mezcla dos husos: en
            # Chile (UTC-4) todo pedido tomado despues de las 20:00 quedaria
            # fechado al dia siguiente.
            #
            # No es un caso raro en este negocio, es el normal: los clientes
            # HORECA piden por la tarde para recibir al dia siguiente. Sin la
            # conversion, la mayor parte de la cartera tendria mal la fecha de
            # ultima compra, mal los dias sin comprar y -lo que mas importa-
            # mal su DIA HABITUAL, que es sobre lo que se arma la lista de
            # recontacto. Un cliente que compra los martes por la tarde
            # figuraria como cliente de miercoles, y se le llamaria el dia
            # equivocado toda la vida del sistema.
            fechas = [_fecha_local(p.date_order, tz) for p in pedidos]
            total = sum(pedidos.mapped('amount_untaxed'))
            n = len(pedidos)

            # Dia de la semana mas frecuente
            conteo = {}
            for f in fechas:
                conteo[f.weekday()] = conteo.get(f.weekday(), 0) + 1
            dia_habitual = max(conteo, key=conteo.get)

            # Frecuencia: media de dias entre pedidos consecutivos
            if n > 1:
                huecos = [(fechas[i] - fechas[i - 1]).days for i in range(1, n)]
                huecos = [h for h in huecos if h > 0]
                frecuencia = sum(huecos) / len(huecos) if huecos else 0.0
            else:
                frecuencia = 0.0

            # Tendencia: 60 dias contra los 60 anteriores
            corte1, corte2 = hoy - timedelta(days=60), hoy - timedelta(days=120)
            reciente = sum(p.amount_untaxed for p in pedidos
                           if p.date_order.date() > corte1)
            previo = sum(p.amount_untaxed for p in pedidos
                         if corte2 < p.date_order.date() <= corte1)
            tendencia = ((reciente - previo) / previo * 100.0) if previo else 0.0

            productos = {}
            for linea in pedidos.order_line:
                if linea.product_id and not linea.display_type:
                    productos[linea.product_id.name] = \
                        productos.get(linea.product_id.name, 0) + 1
            top = ", ".join(sorted(productos, key=productos.get, reverse=True)[:5])

            socio.write({
                'agrogood_order_count': n,
                'agrogood_first_order_date': fechas[0],
                'agrogood_last_order_date': fechas[-1],
                'agrogood_avg_ticket': total / n,
                'agrogood_total_purchased': total,
                'agrogood_avg_days_between': frecuencia,
                'agrogood_usual_weekday': str(dia_habitual),
                'agrogood_volume_trend': tendencia,
                'agrogood_top_products': top,
                'agrogood_customer_status': self._agrogood_status_from(
                    n, (hoy - fechas[-1]).days, frecuencia),
            })
        return True

    @api.model
    def _agrogood_status_from(self, n_pedidos, dias_sin_comprar, frecuencia):
        """Situacion comercial relativa a la frecuencia del propio cliente.

        Un umbral fijo de dias trata igual a quien compra a diario y a quien
        compra una vez al mes, y por eso genera avisos que Ventas aprende a
        ignorar. Aqui el retraso se mide contra el ritmo habitual de cada uno.

        Los multiplicadores son generosos a proposito. En distribucion de
        alimentos, un cliente semanal que lleva dos meses sin pedir sigue
        siendo perfectamente recuperable: darlo por perdido a las seis semanas
        significa dejar de llamarle justo cuando aun se le podia rescatar.
        """
        if n_pedidos <= 1:
            return 'new'
        referencia = frecuencia if frecuencia > 0 else 7.0
        if dias_sin_comprar <= referencia * 1.5:
            return 'active'
        if dias_sin_comprar <= referencia * 3:
            return 'at_risk'
        if dias_sin_comprar <= referencia * 8:
            return 'inactive'
        return 'lost'

    @api.model
    def _cron_agrogood_metrics(self):
        self.search([('agrogood_business_line_id', '!=', False)])\
            ._agrogood_recompute_metrics()
        return True

    def action_agrogood_recompute(self):
        self._agrogood_recompute_metrics()
        return True
