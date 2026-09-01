"""Endpoints de la aplicacion movil de Picker y Conductor.

Se sirven paginas QWeb autonomas, no el cliente web de Odoo. El motivo es
practico: el bundle del backend pesa varios megabytes y esta pensado para
escritorio. Un Picker con una tablet de bodega y un conductor con datos moviles
necesitan que la pantalla cargue en un segundo.

Sobre permisos: cada endpoint comprueba explicitamente que el registro
pertenece a quien lo pide ANTES de actuar. Las reglas de registro ya lo
garantizan -por eso existen-, pero la comprobacion se repite aqui porque
algunas operaciones se ejecutan luego con `sudo()`: validar un albaran exige
permisos de inventario que un conductor no tiene ni debe tener. El patron es
siempre el mismo: autorizar con la identidad real, ejecutar elevado.
"""

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


class AgrogoodPwa(http.Controller):

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _rol(self):
        u = request.env.user
        if u.has_group('agrogood_base.group_agrogood_picker'):
            return 'picker'
        if u.has_group('agrogood_base.group_agrogood_driver'):
            return 'driver'
        return None

    def _accesos(self):
        """Pantallas propias a las que llega este usuario.

        Se devuelve una LISTA y no un rol unico a proposito. Los roles de
        Agrogood se acumulan por necesidad -el encargado de bodega prepara
        pedidos cuando hace falta, y el jefe de logistica hereda ambos-, asi
        que decidir "eres un picker" a partir del primer grupo que coincida
        manda a la pantalla equivocada a media plantilla. Con la lista, quien
        tiene un solo acceso entra directo y quien tiene varios elige.
        """
        u = request.env.user
        def tiene(g):
            return u.has_group('agrogood_base.' + g)

        accesos = []
        if tiene('group_agrogood_sales') or tiene('group_agrogood_general_admin'):
            accesos.append({
                'clave': 'ventas', 'nombre': "Ventas",
                'sub': "Tomar pedidos y ver el dia",
                'url': '/agrogood/ventas',
            })
        if tiene('group_agrogood_picker'):
            accesos.append({
                'clave': 'picker', 'nombre': "Preparacion",
                'sub': "Preparar los pedidos asignados",
                'url': '/agrogood/picker',
            })
        if tiene('group_agrogood_driver'):
            accesos.append({
                'clave': 'driver', 'nombre': "Reparto",
                'sub': "Tu ruta y tus entregas",
                'url': '/agrogood/driver',
            })
        return accesos

    def _mi_cliente(self, partner_id):
        """Cliente valido para vender: con linea comercial y sin hijos sueltos."""
        socio = request.env['res.partner'].browse(int(partner_id))
        socio.check_access('read')
        if not socio.agrogood_business_line_id:
            raise UserError(_(
                "%s no tiene linea comercial asignada, asi que no tiene lista "
                "de precios. Corrigelo antes de tomarle el pedido.",
                socio.display_name))
        return socio

    def _mi_sesion(self, session_id):
        """Devuelve la sesion solo si es del usuario que la pide."""
        sesion = request.env['agrogood.picking.session'].browse(int(session_id))
        sesion.check_access('read')
        if sesion.picker_id != request.env.user:
            raise AccessError(_("Esta preparacion no esta asignada a ti."))
        return sesion

    def _mi_parada(self, stop_id):
        parada = request.env['agrogood.route.stop'].browse(int(stop_id))
        parada.check_access('read')
        if parada.route_id.driver_id != request.env.user:
            raise AccessError(_("Esta entrega no es de tu ruta."))
        return parada

    def _respuesta(self, ok=True, mensaje=None, **extra):
        return dict(ok=ok, mensaje=mensaje, **extra)

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    @http.route('/agrogood/app', type='http', auth='user', website=False)
    def app(self, **kw):
        accesos = self._accesos()
        if not accesos:
            return request.render('agrogood_pwa.sin_rol', {})
        if len(accesos) == 1:
            # Con un solo acceso no se pregunta: el conductor abre la app y ya
            # esta en su ruta. Una pantalla intermedia de un solo boton es un
            # toque de mas, todos los dias.
            return request.redirect(accesos[0]['url'])
        return request.render('agrogood_pwa.elegir', {'accesos': accesos})

    # ------------------------------------------------------------------
    # Picker
    # ------------------------------------------------------------------

    @http.route('/agrogood/picker', type='http', auth='user', website=False)
    def picker_home(self, **kw):
        if self._rol() != 'picker':
            return request.redirect('/agrogood/app')
        Sesion = request.env['agrogood.picking.session']
        return request.render('agrogood_pwa.picker_home', {
            'pendientes': Sesion.search([('state', '=', 'assigned')]),
            'en_curso': Sesion.search([('state', '=', 'in_progress')]),
            'terminadas': Sesion.search(
                [('state', '=', 'done'),
                 ('date_end', '>=', fields.Datetime.to_string(
                     fields.Datetime.now().replace(hour=0, minute=0, second=0)))]),
            'usuario': request.env.user,
        })

    @http.route('/agrogood/picker/<int:session_id>', type='http', auth='user',
                website=False)
    def picker_sesion(self, session_id, **kw):
        sesion = self._mi_sesion(session_id)
        return request.render('agrogood_pwa.picker_sesion', {
            'sesion': sesion,
            'lineas': sesion.picking_id.move_ids.filtered(
                lambda m: m.state != 'cancel'),
        })

    @http.route('/agrogood/api/picker/start', type='json', auth='user')
    def api_start(self, session_id, **kw):
        sesion = self._mi_sesion(session_id)
        try:
            sesion.action_start()
        except (UserError, ValidationError) as e:
            return self._respuesta(False, str(e))
        return self._respuesta(True, _("Preparacion iniciada."))

    @http.route('/agrogood/api/picker/line', type='json', auth='user')
    def api_linea(self, session_id, move_id, status=None, quantity=None,
                  note=None, substitute_id=None, **kw):
        """Registra lo que el Picker marca en una linea.

        Se ejecuta con `sudo()` DESPUES de comprobar que la sesion es suya: el
        Picker no tiene permisos de inventario, y darselos para que pueda
        teclear una cantidad seria abrirle todo el modulo de stock.
        """
        sesion = self._mi_sesion(session_id)
        move = sesion.picking_id.move_ids.filtered(lambda m: m.id == int(move_id))
        if not move:
            return self._respuesta(False, _("Esa linea no es de este pedido."))
        valores = {}
        if status:
            valores['agrogood_line_status'] = status
        if quantity is not None:
            valores['quantity'] = float(quantity)
            valores['picked'] = True
        if note is not None:
            valores['agrogood_incident_note'] = note or False
        if substitute_id:
            valores['agrogood_substitute_product_id'] = int(substitute_id)
        try:
            move.sudo().write(valores)
        except (UserError, ValidationError) as e:
            return self._respuesta(False, str(e))
        move.invalidate_recordset()
        return self._respuesta(
            True,
            desviacion=round(move.sudo().agrogood_weight_deviation, 1),
            estado=move.sudo().agrogood_line_status or '',
        )

    @http.route('/agrogood/api/picker/finish', type='json', auth='user')
    def api_finish(self, session_id, note=None, **kw):
        sesion = self._mi_sesion(session_id)
        if note:
            sesion.sudo().note = note
        try:
            sesion.sudo().action_finish()
        except (UserError, ValidationError) as e:
            return self._respuesta(False, str(e))
        return self._respuesta(True, _("Preparacion terminada."))

    # ------------------------------------------------------------------
    # Conductor
    # ------------------------------------------------------------------

    @http.route('/agrogood/driver', type='http', auth='user', website=False)
    def driver_home(self, **kw):
        if self._rol() != 'driver':
            return request.redirect('/agrogood/app')
        Ruta = request.env['agrogood.route']
        rutas = Ruta.search([('state', 'in', ('planned', 'in_progress'))],
                            order='date, id')
        return request.render('agrogood_pwa.driver_home', {
            'rutas': rutas,
            'usuario': request.env.user,
        })

    @http.route('/agrogood/driver/route/<int:route_id>', type='http', auth='user',
                website=False)
    def driver_ruta(self, route_id, **kw):
        ruta = request.env['agrogood.route'].browse(int(route_id))
        ruta.check_access('read')
        if ruta.driver_id != request.env.user:
            raise AccessError(_("Esta ruta no es tuya."))
        return request.render('agrogood_pwa.driver_ruta', {'ruta': ruta})

    @http.route('/agrogood/driver/stop/<int:stop_id>', type='http', auth='user',
                website=False)
    def driver_parada(self, stop_id, **kw):
        parada = self._mi_parada(stop_id)
        return request.render('agrogood_pwa.driver_parada', {'parada': parada})

    @http.route('/agrogood/api/driver/route_start', type='json', auth='user')
    def api_ruta_start(self, route_id, **kw):
        ruta = request.env['agrogood.route'].browse(int(route_id))
        ruta.check_access('read')
        if ruta.driver_id != request.env.user:
            return self._respuesta(False, _("Esta ruta no es tuya."))
        try:
            ruta.sudo().action_start()
        except (UserError, ValidationError) as e:
            return self._respuesta(False, str(e))
        return self._respuesta(True, _("Ruta iniciada. Buen viaje."))

    @http.route('/agrogood/api/driver/stop', type='json', auth='user')
    def api_parada(self, stop_id, accion, received_by=None, note=None,
                   reason=None, signature=None, photo=None,
                   latitude=None, longitude=None, **kw):
        """Aplica lo que el conductor marca en una parada.

        La ubicacion se guarda tal como la reporta el navegador. No se usa para
        decidir nada -no se comprueba que coincida con la direccion- porque el
        GPS de un telefono falla lo suficiente como para dejar en falso a
        alguien que si entrego. Sirve como evidencia, no como juez.
        """
        parada = self._mi_parada(stop_id)
        p = parada.sudo()
        valores = {}
        if received_by:
            valores['received_by'] = received_by
        if note:
            valores['stop_note'] = note
        if reason:
            valores['failure_reason'] = reason
        if signature:
            valores['signature'] = signature
        if photo:
            valores['photo'] = photo
        if latitude and longitude:
            valores['gps_latitude'] = float(latitude)
            valores['gps_longitude'] = float(longitude)
        if valores:
            p.write(valores)
        # Punto de retorno: si la accion falla, se deshace TODO lo escrito en
        # esta peticion, incluidos los datos de evidencia de arriba. Capturar
        # el error para mostrarlo impide el rollback automatico de Odoo, y sin
        # esto quedarian grabados datos de una entrega que no ocurrio.
        punto = request.env.cr.savepoint(flush=False)
        try:
            if accion == 'on_the_way':
                p.action_on_the_way()
            elif accion == 'arrived':
                p.action_arrived()
            elif accion == 'delivered':
                p.action_delivered()
            elif accion == 'not_delivered':
                p.action_not_delivered()
            elif accion == 'rescheduled':
                p.action_rescheduled()
            else:
                return self._respuesta(False, _("Accion desconocida."))
        except (UserError, ValidationError) as e:
            punto.rollback()
            return self._respuesta(False, str(e))
        punto.close()
        return self._respuesta(True, estado=p.state)

    @http.route('/agrogood/api/driver/route_finish', type='json', auth='user')
    def api_ruta_finish(self, route_id, **kw):
        ruta = request.env['agrogood.route'].browse(int(route_id))
        ruta.check_access('read')
        if ruta.driver_id != request.env.user:
            return self._respuesta(False, _("Esta ruta no es tuya."))
        try:
            ruta.sudo().action_finish()
        except (UserError, ValidationError) as e:
            return self._respuesta(False, str(e))
        return self._respuesta(True, _("Ruta terminada."))


class AgrogoodVentas(http.Controller):
    """Pantallas propias de Ventas.

    Existe por lo mismo que las de Picker y Conductor: el cliente web de Odoo
    es una herramienta de oficina, y tomar un pedido es una tarea de treinta
    segundos que se hace con el telefono en una mano mientras el cliente habla
    por el otro lado. En el formulario estandar hay que abrir el pedido, buscar
    el cliente, anadir linea, buscar producto, escribir cantidad, guardar,
    confirmar. Aqui son tres toques y el precio de SU lista se ve siempre.

    El motor sigue siendo el mismo: se crean `sale.order` normales, con sus
    tarifas, sus impuestos y sus albaranes. Lo que cambia es lo que se ve.
    """

    def _es_ventas(self):
        u = request.env.user
        return (u.has_group('agrogood_base.group_agrogood_sales')
                or u.has_group('agrogood_base.group_agrogood_general_admin'))

    def _hoy(self):
        return fields.Datetime.to_string(
            fields.Datetime.now().replace(hour=0, minute=0, second=0))

    # ------------------------------------------------------------------
    # Pantallas
    # ------------------------------------------------------------------

    @http.route('/agrogood/ventas', type='http', auth='user', website=False)
    def ventas_home(self, **kw):
        if not self._es_ventas():
            return request.redirect('/agrogood/app')
        SO = request.env['sale.order']
        hoy = SO.search([('date_order', '>=', self._hoy()),
                         ('state', 'in', ('sale', 'done'))], order='date_order desc')
        return request.render('agrogood_pwa.ventas_home', {
            'pedidos': hoy,
            'total_hoy': sum(hoy.mapped('amount_untaxed')),
            'llamar': request.env['agrogood.followup'].search(
                [('state', '=', 'pending')], limit=8),
            'usuario': request.env.user,
        })

    @http.route('/agrogood/ventas/nuevo', type='http', auth='user', website=False)
    def ventas_nuevo(self, **kw):
        if not self._es_ventas():
            return request.redirect('/agrogood/app')
        return request.render('agrogood_pwa.ventas_nuevo', {})

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------

    @http.route('/agrogood/api/ventas/clientes', type='json', auth='user')
    def api_clientes(self, q='', **kw):
        if not self._es_ventas():
            raise AccessError(_("No tienes permiso de Ventas."))
        dominio = [('agrogood_business_line_id', '!=', False),
                   ('parent_id', '=', False)]
        if q:
            dominio.append(('name', 'ilike', q))
        socios = request.env['res.partner'].search(dominio, limit=25, order='name')
        return [{
            'id': s.id,
            'nombre': s.name,
            'linea': s.agrogood_business_line_id.name,
            'direccion': s.street or '',
            # Se avisa aqui y no al confirmar: enterarse de que no se le puede
            # facturar cuando el pedido ya esta tomado no sirve de nada.
            'bloqueado': bool(s.agrogood_billing_blocked),
            'motivo': s.agrogood_billing_blocker or '',
        } for s in socios]

    @http.route('/agrogood/api/ventas/productos', type='json', auth='user')
    def api_productos(self, partner_id, q='', **kw):
        if not self._es_ventas():
            raise AccessError(_("No tienes permiso de Ventas."))
        socio = request.env['res.partner'].browse(int(partner_id))
        tarifa = socio.property_product_pricelist
        dominio = [('sale_ok', '=', True)]
        if q:
            dominio = ['&', ('sale_ok', '=', True),
                       '|', ('name', 'ilike', q), ('default_code', 'ilike', q)]
        productos = request.env['product.product'].search(
            dominio, limit=30, order='name')
        salida = []
        for p in productos:
            precio = tarifa._get_product_price(p, 1.0) if tarifa else p.lst_price
            salida.append({
                'id': p.id,
                'nombre': p.name,
                'codigo': p.default_code or '',
                'uom': p.uom_id.name,
                'precio': round(precio),
                'stock': round(p.qty_available, 1),
                'variable': bool(p.agrogood_is_variable_weight),
                # Un producto sin precio en la tarifa del cliente sale a CERO.
                # Odoo no lo impide: pone 0 y sigue. Hoy hay 62 productos asi
                # en la tarifa Minorista y 10 en HORECA, de modo que no es un
                # caso teorico. Se marca aqui para que la pantalla lo apague, y
                # se vuelve a comprobar al crear el pedido.
                'sin_precio': precio <= 0,
            })
        return salida

    @http.route('/agrogood/api/ventas/ultimo', type='json', auth='user')
    def api_ultimo(self, partner_id, **kw):
        """Lo que este cliente llevo la ultima vez.

        En distribucion el pedido de un cliente cambia poco de una semana a
        otra. Partir de lo anterior y corregir dos lineas es mucho mas rapido
        -y se equivoca menos- que teclearlo entero cada vez.
        """
        if not self._es_ventas():
            raise AccessError(_("No tienes permiso de Ventas."))
        anterior = request.env['sale.order'].search([
            ('partner_id', 'child_of', int(partner_id)),
            ('state', 'in', ('sale', 'done')),
        ], order='date_order desc, id desc', limit=1)
        if not anterior:
            return {'ok': False, 'mensaje': _("Este cliente no tiene pedidos anteriores.")}
        return {
            'ok': True,
            'referencia': anterior.name,
            # Se copian producto y cantidad, NUNCA el precio: el de entonces
            # puede no ser el de esta semana, y las tarifas cambian los lunes.
            'lineas': [{'id': l.product_id.id, 'qty': l.product_uom_qty}
                       for l in anterior.order_line
                       if l.product_id and not l.display_type],
        }

    @http.route('/agrogood/api/ventas/crear', type='json', auth='user')
    def api_crear(self, partner_id, lineas, **kw):
        if not self._es_ventas():
            raise AccessError(_("No tienes permiso de Ventas."))
        if not lineas:
            return {'ok': False, 'mensaje': _("El pedido no tiene ninguna linea.")}
        socio = request.env['res.partner'].browse(int(partner_id))

        # La comprobacion se repite en el servidor aunque la pantalla ya apague
        # esos productos: quien construya la peticion a mano entra igual, y
        # regalar mercaderia es un error que no se descubre hasta el cierre del
        # mes. El aviso nombra el producto y la tarifa, que es lo que hace
        # falta para arreglarlo.
        tarifa = socio.property_product_pricelist
        Prod = request.env['product.product']
        sin_precio = []
        for l in lineas:
            prod = Prod.browse(int(l['id']))
            if not tarifa or tarifa._get_product_price(prod, 1.0) <= 0:
                sin_precio.append(prod.display_name)
        if sin_precio:
            salto = chr(10)
            return {'ok': False, 'mensaje': _(
                "Estos productos no tienen precio en la tarifa %(tarifa)s y "
                "saldrian a cero:%(salto)s%(productos)s%(salto)s%(salto)s"
                "Ponles precio antes de venderlos.",
                tarifa=tarifa.name if tarifa else _('del cliente'),
                salto=salto,
                productos=salto.join('  - ' + n for n in sin_precio))}

        try:
            pedido = request.env['sale.order'].create({
                'partner_id': socio.id,
                'order_line': [(0, 0, {
                    'product_id': int(l['id']),
                    'product_uom_qty': float(l['qty']),
                }) for l in lineas if float(l.get('qty') or 0) > 0],
            })
            pedido.action_confirm()
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        estados = dict(pedido._fields['agrogood_state'].selection)
        return {
            'ok': True,
            'id': pedido.id,
            'nombre': pedido.name,
            'total': round(pedido.amount_untaxed),
            'estado': estados.get(pedido.agrogood_state, ''),
            # Cuantas lineas no tienen stock suficiente. Ventas se entera
            # en el momento de tomar el pedido, no al dia siguiente cuando
            # Bodega no encuentra la mercaderia.
            'faltantes': sum(1 for l in pedido.order_line
                             if l.agrogood_shortage_qty > 0),
        }
