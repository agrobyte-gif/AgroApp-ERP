from datetime import timedelta

from odoo import _, api, fields, models


class AgrogoodAlerts(models.AbstractModel):
    """Avisos automaticos hacia el responsable de cada cosa.

    Todos siguen el mismo criterio: **avisar a una persona concreta de algo
    concreto que puede hacer hoy**. Un aviso que no dice quien debe actuar, o
    que llega cuando ya no hay margen, se convierte en ruido y en dos semanas
    nadie lo lee.

    Se apoyan en `mail.activity`, no en correos: la actividad aparece en la
    bandeja del responsable dentro de Odoo, tiene fecha de vencimiento y se
    cierra cuando se resuelve. Un correo se pierde entre otros cien.
    """

    _name = 'agrogood.alerts'
    _description = 'Avisos automaticos de Agrogood'

    # ------------------------------------------------------------------

    @api.model
    def _responsable(self, grupo_xml):
        """Quien debe recibir el aviso de este ambito.

        Se busca por asignacion DIRECTA del grupo, no por `grupo.users`. La
        diferencia importa por la jerarquia de roles: como Jefe de Logistica
        implica Encargado de Bodega, `grupo.users` del grupo de bodega incluye
        tambien a Felipe, y los avisos de bodega le acababan llegando a el en
        lugar de a Matias. `groups_id` en res.users contiene solo lo asignado
        de forma explicita.
        """
        grupo = self.env.ref(grupo_xml, raise_if_not_found=False)
        if not grupo:
            return self.env.user
        directos = self.env['res.users'].search([('groups_id', 'in', grupo.ids)])
        if not directos:
            return grupo.users[0] if grupo.users else self.env.user
        # De haber varios, el que menos grupos Agrogood acumula: es quien tiene
        # ese rol como principal y no como consecuencia de otro mayor.
        cat = self.env.ref('agrogood_base.module_category_agrogood',
                           raise_if_not_found=False)
        if cat:
            return directos.sorted(
                key=lambda u: len(u.groups_id.filtered(
                    lambda g: g.category_id == cat)))[0]
        return directos[0]

    @api.model
    def _crear_actividad(self, registro, usuario, resumen, nota, dias=0):
        """Crea la actividad si no hay ya una igual sin cerrar.

        La comprobacion de duplicado es lo que hace util un aviso diario: sin
        ella, un pedido atrasado genera una actividad nueva cada manana y la
        bandeja del responsable queda inservible en una semana.
        """
        Actividad = self.env['mail.activity']
        modelo = self.env['ir.model']._get(registro._name)
        existe = Actividad.search([
            ('res_model_id', '=', modelo.id),
            ('res_id', '=', registro.id),
            ('summary', '=', resumen),
        ], limit=1)
        if existe:
            return False
        return Actividad.create({
            'res_model_id': modelo.id,
            'res_id': registro.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'summary': resumen,
            'note': nota,
            'user_id': usuario.id,
            'date_deadline': fields.Date.context_today(self) + timedelta(days=dias),
        })

    # ------------------------------------------------------------------
    # Avisos
    # ------------------------------------------------------------------

    @api.model
    def _cron_pedidos_atrasados(self):
        """Pedidos cuya fecha de entrega ya paso y siguen sin entregar."""
        hoy = fields.Datetime.now()
        responsable = self._responsable('agrogood_base.group_agrogood_logistics_manager')
        pedidos = self.env['sale.order'].search([
            ('state', '=', 'sale'),
            ('commitment_date', '<', hoy),
            ('agrogood_state', 'not in',
             ('delivered', 'invoiced', 'closed', 'cancelled')),
        ])
        n = 0
        for p in pedidos:
            etiqueta = dict(p._fields['agrogood_state'].selection)[p.agrogood_state]
            if self._crear_actividad(
                p, responsable,
                _("Pedido atrasado"),
                _("%(pedido)s de %(cliente)s deberia haberse entregado el "
                  "%(fecha)s y sigue en '%(estado)s'.",
                  pedido=p.name, cliente=p.partner_id.display_name,
                  fecha=fields.Date.to_string(p.commitment_date.date()),
                  estado=etiqueta),
            ):
                n += 1
        return n

    @api.model
    def _cron_faltantes_sin_solicitud(self):
        """Pedidos con faltante que nadie ha pasado a la pizarra de Compras.

        Es el hueco por el que se escapa el trabajo: el faltante se detecta
        solo, pero convertirlo en solicitud es una accion manual, y si nadie la
        hace el pedido se queda esperando mercaderia que nadie va a comprar.
        """
        responsable = self._responsable('agrogood_base.group_agrogood_logistics_manager')
        pedidos = self.env['sale.order'].search([
            ('state', '=', 'sale'),
            ('agrogood_has_shortage', '=', True),
        ])
        n = 0
        for p in pedidos:
            abiertas = self.env['agrogood.purchase.request'].search_count([
                ('sale_order_id', '=', p.id),
                ('state', 'not in', ('cancelled', 'rejected', 'not_found')),
            ])
            if abiertas:
                continue
            if self._crear_actividad(
                p, responsable,
                _("Faltante sin pedir"),
                _("%(pedido)s tiene %(n)s linea(s) con faltante y ninguna "
                  "solicitud de compra abierta. Usa 'Pedir reposicion'.",
                  pedido=p.name, n=p.agrogood_shortage_count),
            ):
                n += 1
        return n

    @api.model
    def _cron_solicitudes_estancadas(self):
        """Solicitudes de compra que llevan dias sin moverse."""
        limite = fields.Date.context_today(self) - timedelta(days=2)
        solicitudes = self.env['agrogood.purchase.request'].search([
            ('state', 'in', ('pending', 'searching', 'quoting')),
            ('date_needed', '<=', limite),
        ])
        n = 0
        for s in solicitudes:
            if self._crear_actividad(
                s, s.user_id or self._responsable(
                    'agrogood_base.group_agrogood_purchase'),
                _("Solicitud estancada"),
                _("%(ref)s (%(producto)s) se necesitaba para el %(fecha)s y "
                  "sigue en '%(estado)s'.",
                  ref=s.name, producto=s.product_id.display_name,
                  fecha=fields.Date.to_string(s.date_needed),
                  estado=dict(s._fields['state'].selection)[s.state]),
            ):
                n += 1
        return n

    @api.model
    def _cron_lotes_por_vencer(self):
        """Mercaderia perecible a punto de perderse.

        Se avisa cuando queda stock del lote: un lote vencido que ya se vendio
        entero no es un problema, y avisar de el enseniaria a ignorar el aviso.
        """
        hoy = fields.Datetime.now()
        responsable = self._responsable('agrogood_base.group_agrogood_warehouse')
        lotes = self.env['stock.lot'].search([
            ('expiration_date', '!=', False),
            ('alert_date', '<=', hoy),
            ('product_qty', '>', 0),
        ])
        n = 0
        for lote in lotes:
            dias = (lote.expiration_date.date() - fields.Date.context_today(self)).days
            cuando = (_("vence hoy") if dias == 0
                      else _("vencio hace %s dias", abs(dias)) if dias < 0
                      else _("vence en %s dias", dias))
            if self._crear_actividad(
                lote, responsable,
                _("Lote por vencer"),
                _("Quedan %(cant)s %(uom)s de %(producto)s (lote %(lote)s) y "
                  "%(cuando)s. Da salida prioritaria o registra la merma.",
                  cant=f"{lote.product_qty:g}", uom=lote.product_id.uom_id.name,
                  producto=lote.product_id.display_name, lote=lote.name,
                  cuando=cuando),
            ):
                n += 1
        return n

    @api.model
    def _cron_stock_bajo(self):
        """Productos habituales que se han quedado sin stock.

        Solo se miran los que se vendieron en el ultimo mes: avisar de que no
        hay stock de algo que nadie pide es exactamente el tipo de aviso que
        hace que se dejen de mirar todos los demas.
        """
        desde = fields.Datetime.now() - timedelta(days=30)
        lineas = self.env['sale.order.line'].search([
            ('order_id.state', 'in', ('sale', 'done')),
            ('order_id.date_order', '>=', desde),
        ])
        habituales = lineas.product_id.filtered(
            lambda p: p.is_storable and p.qty_available <= 0)
        responsable = self._responsable('agrogood_base.group_agrogood_purchase')
        n = 0
        for prod in habituales:
            if self._crear_actividad(
                prod.product_tmpl_id, responsable,
                _("Sin stock"),
                _("%(producto)s se vendio en el ultimo mes y esta a cero. "
                  "Conviene reponer antes de que un cliente lo pida.",
                  producto=prod.display_name),
                dias=1,
            ):
                n += 1
        return n

    @api.model
    def _cron_todos(self):
        """Punto de entrada unico, para tener una sola tarea programada."""
        resultado = {
            'pedidos atrasados': self._cron_pedidos_atrasados(),
            'faltantes sin pedir': self._cron_faltantes_sin_solicitud(),
            'solicitudes estancadas': self._cron_solicitudes_estancadas(),
            'lotes por vencer': self._cron_lotes_por_vencer(),
            'sin stock': self._cron_stock_bajo(),
        }
        total = sum(resultado.values())
        if total:
            detalle = ", ".join(f"{k}: {v}" for k, v in resultado.items() if v)
            self.env['ir.logging'].sudo().create({
                'name': 'agrogood.alerts', 'type': 'server',
                'level': 'INFO', 'dbname': self.env.cr.dbname,
                'message': f"Avisos generados -> {detalle}",
                'path': 'agrogood_alerts', 'func': '_cron_todos', 'line': '0',
            })
        return resultado
