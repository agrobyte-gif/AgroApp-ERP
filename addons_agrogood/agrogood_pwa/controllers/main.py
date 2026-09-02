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

# Los puntos de la revision viven en agrogood_logistics, que es de donde
# son. Se importan en lugar de repetirlos aqui: dos listas que hay que
# mantener iguales acaban siendo distintas.
from odoo.addons.agrogood_logistics.models.agrogood_vehicle_check import PUNTOS

# El validador de RUT vive con las identidades de pago, que es donde
# se escribio. Se importa en lugar de copiarlo: dos validadores de RUT
# acaban discrepando, y el que se queda viejo es siempre el de la copia.
from odoo.addons.agrogood_crm_reactivation.models.agrogood_payer import (
    normalizar_rut,
)


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
        if tiene('group_agrogood_general_admin'):
            accesos.append({
                'clave': 'direccion', 'nombre': "Direccion",
                'sub': "Las cifras del dia",
                'url': '/agrogood/direccion',
            })
        if tiene('group_agrogood_sales') or tiene('group_agrogood_general_admin'):
            accesos.append({
                'clave': 'ventas', 'nombre': "Ventas",
                'sub': "Tomar pedidos y ver el dia",
                'url': '/agrogood/ventas',
            })
        if tiene('group_agrogood_sales') or tiene('group_agrogood_general_admin'):
            accesos.append({
                'clave': 'cobranza', 'nombre': "Cobranza",
                'sub': "A quien llamar y cuanto debe",
                'url': '/agrogood/cobranza',
            })
        if tiene('group_agrogood_purchase'):
            accesos.append({
                'clave': 'compras', 'nombre': "Compras",
                'sub': "La pizarra: que hay que conseguir",
                'url': '/agrogood/compras',
            })
        if tiene('group_agrogood_logistics_manager'):
            accesos.append({
                'clave': 'logistica', 'nombre': "Logistica",
                'sub': "Repartir el trabajo y armar las rutas",
                'url': '/agrogood/logistica',
            })
        if tiene('group_agrogood_warehouse'):
            accesos.append({
                'clave': 'bodega', 'nombre': "Bodega",
                'sub': "Recibir mercaderia y registrar mermas",
                'url': '/agrogood/bodega',
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

    @http.route('/agrogood/driver/route/<int:route_id>/revision',
                type='http', auth='user', website=False)
    def driver_revision(self, route_id, **kw):
        ruta = request.env['agrogood.route'].browse(int(route_id))
        ruta.check_access('read')
        if ruta.driver_id != request.env.user:
            return request.redirect('/agrogood/driver')
        return request.render('agrogood_pwa.driver_revision', {
            'ruta': ruta,
            'puntos': PUNTOS,
            'hecha': ruta.check_ids[:1],
        })

    @http.route('/agrogood/api/driver/revision', type='json', auth='user')
    def api_revision(self, route_id, marcados, note=None, odometer=None, **kw):
        """Guarda la revision del vehiculo antes de salir.

        Se autoriza con la identidad real -la ruta tiene que ser suya- y se
        escribe elevado, porque crear el documento toca el historial de la ruta
        y un conductor no tiene por que poder escribir en ella.
        """
        ruta = request.env['agrogood.route'].browse(int(route_id))
        ruta.check_access('read')
        if ruta.driver_id != request.env.user:
            return self._respuesta(False, _("Esta ruta no es tuya."))
        if not ruta.vehicle_id:
            return self._respuesta(False, _(
                "La ruta no tiene vehiculo asignado. Avisa a Logistica."))
        if ruta.check_ids:
            return self._respuesta(False, _("Esta ruta ya tiene su revision."))

        vals = {
            'route_id': ruta.id,
            'vehicle_id': ruta.vehicle_id.id,
            'driver_id': request.env.user.id,
            'note': (note or '').strip(),
        }
        if odometer:
            vals['odometer'] = float(odometer)
        marcados = set(marcados or [])
        for clave, _etiqueta in PUNTOS:
            vals['check_%s' % clave] = clave in marcados
        try:
            revision = request.env['agrogood.vehicle.check'].sudo().create(vals)
        except (UserError, ValidationError) as e:
            return self._respuesta(False, str(e))
        return self._respuesta(
            True,
            _("Revision guardada. Ya puedes iniciar la ruta.")
            if revision.state == 'ok'
            else _("Revision guardada con novedad. Logistica ya tiene el aviso."),
            estado=revision.state)

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


    # ------------------------------------------------------------------
    # Cambiar un pedido ya tomado
    # ------------------------------------------------------------------

    def _mi_pedido(self, order_id):
        pedido = request.env['sale.order'].browse(int(order_id))
        pedido.check_access('read')
        return pedido

    @http.route('/agrogood/ventas/pedido/<int:order_id>', type='http',
                auth='user', website=False)
    def ventas_pedido(self, order_id, **kw):
        if not self._es_ventas():
            return request.redirect('/agrogood/app')
        pedido = self._mi_pedido(order_id)
        estados = dict(pedido._fields['agrogood_state'].selection)
        return request.render('agrogood_pwa.ventas_pedido', {
            'pedido': pedido,
            'etapa': estados.get(pedido.agrogood_state, ''),
            'usuario': request.env.user,
        })

    @http.route('/agrogood/api/ventas/modificar', type='json', auth='user')
    def api_modificar(self, order_id, lineas, **kw):
        """Deja el pedido con EXACTAMENTE las lineas que llegan.

        Se manda el pedido entero y no una lista de cambios. Con dos personas
        editando el mismo pedido desde dos telefonos, una lista de cambios se
        aplica sobre un pedido que ya no es el que se vio, y el resultado no es
        ninguno de los dos. Mandarlo entero hace que gane el ultimo que guarda,
        que es un resultado que al menos se puede explicar por telefono.

        Cantidad cero borra la linea: en una pantalla de telefono es el gesto
        natural, y evita un boton de borrar por linea.
        """
        if not self._es_ventas():
            raise AccessError(_("No tienes permiso de Ventas."))
        pedido = self._mi_pedido(order_id)
        try:
            pedido._agrogood_check_editable()
        except UserError as e:
            return {'ok': False, 'mensaje': str(e)}

        pedidas = {}
        for l in lineas or []:
            cantidad = float(l.get('qty') or 0)
            if cantidad > 0:
                pedidas[int(l['id'])] = cantidad
        if not pedidas:
            return {'ok': False, 'mensaje': _(
                "El pedido quedaria sin ninguna linea. Si el cliente lo "
                "anulo, usa Anular pedido: deja constancia de que se anulo, "
                "en vez de un pedido vacio que nadie sabe que fue.")}

        # El mismo control que al crear: un producto sin precio en la tarifa
        # del cliente saldria a cero, y regalar mercaderia no se descubre hasta
        # el cierre del mes.
        tarifa = pedido.partner_id.property_product_pricelist
        Prod = request.env['product.product']
        sin_precio = [Prod.browse(i).display_name for i in pedidas
                      if not tarifa or tarifa._get_product_price(
                          Prod.browse(i), 1.0) <= 0]
        if sin_precio:
            salto = chr(10)
            return {'ok': False, 'mensaje': _(
                "Estos productos no tienen precio en la tarifa %(tarifa)s y "
                "saldrian a cero:%(salto)s%(productos)s",
                tarifa=tarifa.name if tarifa else _('del cliente'),
                salto=salto,
                productos=salto.join('  - ' + n for n in sin_precio))}

        try:
            # Elevado: cambiar un pedido confirmado reajusta las reservas de
            # stock, y eso son permisos de inventario que Ventas no tiene ni
            # debe tener. Se autoriza con la identidad real -arriba- y se
            # ejecuta elevado, que es el patron de todos los endpoints.
            elevado = pedido.sudo()
            for linea in elevado.order_line:
                producto = linea.product_id.id
                if producto in pedidas:
                    if linea.product_uom_qty != pedidas[producto]:
                        linea.product_uom_qty = pedidas.pop(producto)
                    else:
                        pedidas.pop(producto)
                    continue
                # Quitar una linea de un pedido YA CONFIRMADO no es borrarla.
                # Odoo no deja, y con razon: esa linea puede tener movimientos
                # de stock detras. Se deja en cero, que es su forma de decir
                # que eso ya no se pide sin perder el rastro de que estuvo.
                try:
                    linea.unlink()
                except (UserError, ValidationError):
                    linea.product_uom_qty = 0.0
            for producto, cantidad in pedidas.items():
                request.env['sale.order.line'].sudo().create({
                    'order_id': elevado.id,
                    'product_id': producto,
                    'product_uom_qty': cantidad,
                })
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}

        pedido.invalidate_recordset()
        return {
            'ok': True,
            'mensaje': _("%(pedido)s actualizado.", pedido=pedido.name),
            'total': round(pedido.amount_untaxed),
            'faltantes': sum(1 for l in pedido.order_line
                             if l.agrogood_shortage_qty > 0),
        }

    @http.route('/agrogood/api/ventas/anular', type='json', auth='user')
    def api_anular(self, order_id, motivo=None, **kw):
        """Anula el pedido y deja escrito por que.

        El motivo no es burocracia: un pedido anulado sin explicacion aparece
        en el historial del cliente como si nunca hubiera comprado, y el CRM
        acaba llamandolo por una racha que no existio.
        """
        if not self._es_ventas():
            raise AccessError(_("No tienes permiso de Ventas."))
        pedido = self._mi_pedido(order_id)
        if not (motivo or '').strip():
            return {'ok': False,
                    'mensaje': _("Anota por que se anula.")}
        try:
            pedido._agrogood_check_editable()
            pedido.sudo()._action_cancel()
            pedido.sudo().message_post(
                body=_("Anulado desde Ventas: %s", motivo.strip()))
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        return {'ok': True,
                'mensaje': _("%(pedido)s anulado.", pedido=pedido.name)}

    # ------------------------------------------------------------------
    # Dar de alta un cliente
    # ------------------------------------------------------------------

    @http.route('/agrogood/ventas/cliente', type='http', auth='user',
                website=False)
    def ventas_cliente_nuevo(self, **kw):
        if not self._es_ventas():
            return request.redirect('/agrogood/app')
        return request.render('agrogood_pwa.ventas_cliente', {
            'lineas': request.env['agrogood.business.line'].search([]),
        })

    @http.route('/agrogood/api/ventas/cliente_nuevo', type='json', auth='user')
    def api_cliente_nuevo(self, nombre, business_line_id, vat=None,
                          street=None, city=None, mobile=None, **kw):
        """Crea el cliente con lo minimo para poder venderle.

        La linea comercial es obligatoria porque de ella sale su lista de
        precios: sin ella el primer pedido saldria a cero. El RUT no lo es -se
        puede vender y repartir sin el, solo no facturar-, pero si viene se
        valida el digito verificador aqui mismo, que es cien veces mas barato
        que descubrirlo el dia que se emite la factura.
        """
        if not self._es_ventas():
            raise AccessError(_("No tienes permiso de Ventas."))
        nombre = (nombre or '').strip()
        if len(nombre) < 3:
            return {'ok': False, 'mensaje': _("Falta el nombre del cliente.")}
        if not business_line_id:
            return {'ok': False, 'mensaje': _(
                "Elige la linea comercial: de ella sale la lista de precios, "
                "y sin ella el pedido saldria a cero.")}

        Socio = request.env['res.partner']
        repetido = Socio.search([('name', '=ilike', nombre),
                                 ('parent_id', '=', False)], limit=1)
        if repetido:
            return {'ok': False, 'mensaje': _(
                "Ya existe un cliente que se llama %(nombre)s. Si es otro "
                "local del mismo negocio, ponle el nombre de la sucursal.",
                nombre=repetido.display_name)}

        vals = {
            'name': nombre,
            'is_company': True,
            'customer_rank': 1,
            'agrogood_business_line_id': int(business_line_id),
            'country_id': request.env.ref('base.cl').id,
        }
        if (vat or '').strip():
            normalizado = normalizar_rut(vat)
            if not normalizado:
                return {'ok': False, 'mensaje': _(
                    "%(rut)s no es un RUT valido: no cuadra el digito "
                    "verificador. Revisalo con el cliente delante, que es "
                    "cuando se puede preguntar.", rut=vat)}
            en_uso = Socio.search([('vat', '=', normalizado)], limit=1)
            if en_uso:
                return {'ok': False, 'mensaje': _(
                    "Ese RUT ya es de %(cliente)s.",
                    cliente=en_uso.display_name)}
            vals['vat'] = normalizado
        for campo, valor in (('street', street), ('city', city),
                             ('mobile', mobile)):
            if (valor or '').strip():
                vals[campo] = valor.strip()

        try:
            socio = Socio.sudo().create(vals)
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        return {
            'ok': True,
            'id': socio.id,
            'nombre': socio.display_name,
            'mensaje': _("%(cliente)s creado. Ya se le puede tomar pedido.",
                         cliente=socio.display_name),
            'sin_rut': not socio.vat,
        }


class AgrogoodBodega(http.Controller):
    """Pantallas propias de Bodega.

    Recibir una compra en Odoo son tres pantallas: el albaran, la pestana de
    operaciones detalladas y, si el producto lleva caducidad, una linea por
    lote. Matias lo hace con el camion del proveedor esperando y las manos
    frias. Aqui es una sola lista: cantidad, lote y vencimiento en la misma
    fila, y validar.
    """

    def _es_bodega(self):
        u = request.env.user
        return (u.has_group('agrogood_base.group_agrogood_warehouse')
                or u.has_group('agrogood_base.group_agrogood_general_admin'))

    def _mi_recepcion(self, picking_id):
        p = request.env['stock.picking'].browse(int(picking_id))
        p.check_access('read')
        if p.picking_type_id.code != 'incoming':
            raise UserError(_("%s no es una recepcion.", p.name))
        return p

    @http.route('/agrogood/bodega', type='http', auth='user', website=False)
    def bodega_home(self, **kw):
        if not self._es_bodega():
            return request.redirect('/agrogood/app')
        Pick = request.env['stock.picking']
        return request.render('agrogood_pwa.bodega_home', {
            'recepciones': Pick.search(
                [('picking_type_id.code', '=', 'incoming'),
                 ('state', 'not in', ('done', 'cancel'))], order='scheduled_date'),
            'preparando': request.env['agrogood.picking.session'].search(
                [('state', 'in', ('assigned', 'in_progress'))]),
            'por_vencer': request.env['stock.lot'].search(
                [('expiration_date', '!=', False)], order='expiration_date', limit=6),
            'usuario': request.env.user,
        })

    @http.route('/agrogood/bodega/recepcion/<int:picking_id>',
                type='http', auth='user', website=False)
    def bodega_recepcion(self, picking_id, **kw):
        if not self._es_bodega():
            return request.redirect('/agrogood/app')
        p = self._mi_recepcion(picking_id)
        return request.render('agrogood_pwa.bodega_recepcion', {
            'picking': p,
            'lineas': p.move_ids.filtered(lambda m: m.state != 'cancel'),
        })

    @http.route('/agrogood/bodega/merma', type='http', auth='user',
                website=False)
    def bodega_merma(self, **kw):
        if not self._es_bodega():
            return request.redirect('/agrogood/app')
        return request.render('agrogood_pwa.bodega_merma', {})

    @http.route('/agrogood/api/bodega/recibir', type='json', auth='user')
    def api_recibir(self, picking_id, lineas, **kw):
        """Anota lo que llego de verdad y valida.

        La cantidad recibida se escribe en la linea; si el producto lleva lote,
        se crea con su fecha de vencimiento en el mismo gesto. Separar las dos
        cosas -recibir hoy, poner el lote despues- es como se pierde la
        trazabilidad: nadie vuelve.
        """
        if not self._es_bodega():
            raise AccessError(_("No tienes permiso de Bodega."))
        p = self._mi_recepcion(picking_id)
        Move = request.env['stock.move']

        # Primero se comprueba TODO y despues se escribe. Al reves, un lote que
        # falta a mitad de la lista deja media recepcion anotada y media no, y
        # nadie sabe por donde iba.
        faltan_lote = []
        for l in lineas:
            mov = Move.browse(int(l['move_id']))
            if mov.picking_id != p:
                raise AccessError(_("Esa linea no es de esta recepcion."))
            cantidad = float(l.get('qty') or 0)
            if (mov.product_id.tracking == 'lot' and cantidad > 0
                    and not (l.get('lote') or '').strip()):
                faltan_lote.append(mov.product_id.display_name)
        if faltan_lote:
            salto = chr(10)
            return {'ok': False, 'mensaje': _(
                "Estos productos llevan control de caducidad y necesitan "
                "numero de lote:%(salto)s%(lista)s",
                salto=salto,
                lista=salto.join('  - ' + n for n in faltan_lote))}

        for l in lineas:
            mov = Move.browse(int(l['move_id']))
            cantidad = float(l.get('qty') or 0)
            mov.move_line_ids.unlink()
            if cantidad <= 0:
                mov.quantity = 0
                continue
            vals = {
                'move_id': mov.id,
                'product_id': mov.product_id.id,
                'location_id': mov.location_id.id,
                'location_dest_id': mov.location_dest_id.id,
                'quantity': cantidad,
                'picked': True,
            }
            if mov.product_id.tracking == 'lot':
                vals['lot_name'] = (l.get('lote') or '').strip()
                if l.get('vence'):
                    # Mediodia y no medianoche: guardado en UTC, una fecha a las
                    # 00:00 se lee como el dia anterior en Chile, y una caducidad
                    # corrida un dia manda a la basura mercaderia buena.
                    vals['expiration_date'] = l['vence'] + " 12:00:00"
            request.env['stock.move.line'].create(vals)

        try:
            resultado = p.button_validate()
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}

        # Odoo devuelve un asistente cuando queda cantidad sin recibir: es la
        # pregunta del pedido en espera. Se responde que si -lo que falta se
        # sigue debiendo- porque una compra incompleta no cierra la orden.
        if isinstance(resultado, dict) and resultado.get('res_model'):
            asistente = request.env[resultado['res_model']].with_context(
                **resultado.get('context', {})).create({})
            if hasattr(asistente, 'process'):
                asistente.process()
            elif hasattr(asistente, 'action_confirm'):
                asistente.action_confirm()
        p.invalidate_recordset()
        return {'ok': True, 'estado': p.state,
                'mensaje': _("%s recibido.", p.name)}

    @http.route('/agrogood/api/bodega/productos', type='json', auth='user')
    def api_bodega_productos(self, q='', **kw):
        if not self._es_bodega():
            raise AccessError(_("No tienes permiso de Bodega."))
        dominio = [('is_storable', '=', True)]
        if q:
            dominio = ['&', ('is_storable', '=', True),
                       '|', ('name', 'ilike', q), ('default_code', 'ilike', q)]
        return [{
            'id': p.id,
            'nombre': p.name,
            'codigo': p.default_code or '',
            'uom': p.uom_id.name,
            'stock': round(p.qty_available, 1),
            # Sin esto la pantalla no sabe que tiene que pedir el lote, y una
            # merma sin lote se queda en borrador sin registrar nada.
            'lleva_lote': p.tracking == 'lot',
        } for p in request.env['product.product'].search(
            dominio, limit=25, order='name')]

    @http.route('/agrogood/api/bodega/lotes', type='json', auth='user')
    def api_lotes(self, product_id, **kw):
        """Lotes de ese producto con existencias, el que antes vence primero.

        Se ordenan por vencimiento porque lo que se merma es casi siempre lo
        mas viejo, y ponerlo arriba evita que Bodega tenga que buscarlo.
        """
        if not self._es_bodega():
            raise AccessError(_("No tienes permiso de Bodega."))
        quants = request.env['stock.quant'].search([
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ])
        salida = []
        for q in quants.sorted(lambda x: (x.lot_id.expiration_date or fields.Datetime.now())):
            if not q.lot_id:
                continue
            vence = q.lot_id.expiration_date
            salida.append({
                'id': q.lot_id.id,
                'nombre': q.lot_id.name,
                'cantidad': round(q.quantity, 1),
                'vence': fields.Datetime.context_timestamp(
                    q.lot_id, vence).strftime('%d/%m/%Y') if vence else '',
            })
        return salida

    @http.route('/agrogood/api/bodega/responsables', type='json', auth='user')
    def api_responsables(self, q='', **kw):
        """Proveedores y transportistas, para las mermas que se reclaman."""
        if not self._es_bodega():
            raise AccessError(_("No tienes permiso de Bodega."))
        dominio = [('supplier_rank', '>', 0)]
        if q:
            dominio = ['&', ('supplier_rank', '>', 0), ('name', 'ilike', q)]
        return [{'id': s.id, 'nombre': s.name}
                for s in request.env['res.partner'].search(
                    dominio, limit=20, order='name')]

    @http.route('/agrogood/api/bodega/merma', type='json', auth='user')
    def api_merma(self, product_id, qty, reason, note=None, partner_id=None,
                  lot_id=None, **kw):
        """Registra una merma con su motivo tipificado.

        El motivo no es decorativo: separa lo que hay que reclamar al proveedor
        de lo que se perdio en casa. Sin el, todas las mermas parecen lo mismo y
        nadie reclama nada.
        """
        if not self._es_bodega():
            raise AccessError(_("No tienes permiso de Bodega."))
        alm = request.env['stock.warehouse'].search([], limit=1)
        producto = request.env['product.product'].browse(int(product_id))
        # Un producto con control de caducidad NO se puede mermar sin decir de
        # que lote: Odoo no sabe de donde descontarlo y deja la merma en
        # borrador sin avisar de nada. Son 115 de los 195 productos.
        if producto.tracking == 'lot' and not lot_id:
            return {'ok': False, 'mensaje': _(
                "%s lleva control de caducidad: hay que decir de que lote se "
                "perdio.", producto.display_name)}
        try:
            merma = request.env['stock.scrap'].create({
                'product_id': int(product_id),
                'lot_id': int(lot_id) if lot_id else False,
                'scrap_qty': float(qty),
                'location_id': alm.lot_stock_id.id,
                'agrogood_reason': reason,
                'agrogood_reason_note': (note or '').strip(),
                # Las mermas reclamables exigen a quien se le reclama: sin ese
                # dato la perdida se asume y ya no se recupera. La pantalla lo
                # pide, y aqui se vuelve a exigir.
                'agrogood_partner_id': int(partner_id) if partner_id else False,
            })
            merma.action_validate()
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        return {'ok': True, 'mensaje': _("Merma registrada: %s", merma.name)}


class AgrogoodLogistica(http.Controller):
    """Pantallas propias de Logistica.

    Felipe reparte el trabajo del dia y arma las rutas. En Odoo eso son dos
    listas, un asistente y un formulario con lineas, y hay que saber donde
    esta cada cosa. Aqui son dos pantallas: a quien le toca preparar, y quien
    lleva que.

    Se reutilizan los modelos y los asistentes que ya existen -no se duplica
    logica-: lo que cambia es que se llega a ellos en dos toques.
    """

    def _es_logistica(self):
        u = request.env.user
        return (u.has_group('agrogood_base.group_agrogood_logistics_manager')
                or u.has_group('agrogood_base.group_agrogood_general_admin'))

    @http.route('/agrogood/logistica', type='http', auth='user', website=False)
    def logistica_home(self, **kw):
        if not self._es_logistica():
            return request.redirect('/agrogood/app')
        Pick = request.env['stock.picking']
        Sesion = request.env['agrogood.picking.session']
        salidas = Pick.search([('picking_type_id.code', '=', 'outgoing'),
                               ('state', 'not in', ('done', 'cancel'))])
        return request.render('agrogood_pwa.logistica_home', {
            'sin_picker': salidas.filtered(lambda p: not p.agrogood_session_id),
            'preparando': Sesion.search(
                [('state', 'in', ('assigned', 'in_progress'))]),
            'listos': salidas.filtered(
                lambda p: p.agrogood_session_id
                and p.agrogood_session_id[0].state == 'done'
                and not p.agrogood_route_id),
            'rutas': request.env['agrogood.route'].search(
                [('state', 'in', ('draft', 'planned', 'in_progress'))],
                order='date, id'),
            'usuario': request.env.user,
        })

    @http.route('/agrogood/logistica/asignar', type='http', auth='user',
                website=False)
    def logistica_asignar(self, **kw):
        if not self._es_logistica():
            return request.redirect('/agrogood/app')
        Pick = request.env['stock.picking']
        grupo = request.env.ref('agrogood_base.group_agrogood_picker',
                                raise_if_not_found=False)
        pickers = request.env['res.users'].search(
            [('groups_id', 'in', grupo.ids)]) if grupo else request.env['res.users']
        Sesion = request.env['agrogood.picking.session']
        carga = {
            p.id: Sesion.search_count([('picker_id', '=', p.id),
                                       ('state', 'in', ('assigned', 'in_progress'))])
            for p in pickers
        }
        return request.render('agrogood_pwa.logistica_asignar', {
            'albaranes': Pick.search(
                [('picking_type_id.code', '=', 'outgoing'),
                 ('state', 'not in', ('done', 'cancel'))]).filtered(
                     lambda p: not p.agrogood_session_id),
            'pickers': pickers,
            'carga': carga,
        })

    @http.route('/agrogood/logistica/ruta', type='http', auth='user',
                website=False)
    def logistica_ruta(self, **kw):
        if not self._es_logistica():
            return request.redirect('/agrogood/app')
        Pick = request.env['stock.picking']
        grupo = request.env.ref('agrogood_base.group_agrogood_driver',
                                raise_if_not_found=False)
        # Solo se ofrecen los albaranes YA PREPARADOS. Meter en una ruta algo
        # que el Picker no ha terminado manda al conductor a buscar una caja
        # que todavia no existe.
        listos = Pick.search(
            [('picking_type_id.code', '=', 'outgoing'),
             ('state', 'not in', ('done', 'cancel'))]).filtered(
                 lambda p: p.agrogood_session_id
                 and p.agrogood_session_id[0].state == 'done'
                 and not p.agrogood_route_id)
        return request.render('agrogood_pwa.logistica_ruta', {
            'albaranes': listos,
            'conductores': request.env['res.users'].search(
                [('groups_id', 'in', grupo.ids)]) if grupo else request.env['res.users'],
            'vehiculos': request.env['fleet.vehicle'].search([]),
            'hoy': fields.Date.to_string(fields.Date.context_today(request.env.user)),
        })

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    @http.route('/agrogood/api/logistica/asignar', type='json', auth='user')
    def api_asignar(self, picking_ids, picker_id, **kw):
        """Reparte albaranes a un Picker.

        Se apoya en el asistente que ya existe en lugar de crear las sesiones a
        mano: ahi vive la comprobacion de que ninguno tenga ya Picker asignado,
        y duplicarla seria tener dos sitios donde arreglarla.
        """
        if not self._es_logistica():
            raise AccessError(_("No tienes permiso de Logistica."))
        if not picking_ids:
            return {'ok': False, 'mensaje': _("No has elegido ningun pedido.")}
        try:
            asistente = request.env['agrogood.assign.picker'].create({
                'picking_ids': [(6, 0, [int(i) for i in picking_ids])],
                'picker_id': int(picker_id),
            })
            asistente.action_assign()
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        n = len(picking_ids)
        return {'ok': True, 'mensaje': _(
            "%(n)s pedido(s) asignados. Ya los ve en su telefono.", n=n)}

    @http.route('/agrogood/api/logistica/ruta', type='json', auth='user')
    def api_crear_ruta(self, picking_ids, driver_id, vehicle_id, fecha=None, **kw):
        if not self._es_logistica():
            raise AccessError(_("No tienes permiso de Logistica."))
        if not picking_ids:
            return {'ok': False, 'mensaje': _("La ruta no lleva ninguna entrega.")}
        Ruta = request.env['agrogood.route']
        try:
            ruta = Ruta.create({
                'driver_id': int(driver_id),
                'vehicle_id': int(vehicle_id),
                'date': fecha or fields.Date.context_today(request.env.user),
            })
            # `agrogood_route_id` es un campo CALCULADO a partir de la parada:
            # no se le escribe. Se usa el asistente que ya existe, que ademas
            # comprueba que los albaranes esten preparados -meter en el camion
            # un pedido a medio preparar es la forma mas rapida de que salga
            # incompleto- y numera las paradas.
            request.env['agrogood.route.add.pickings'].create({
                'route_id': ruta.id,
                'picking_ids': [(6, 0, [int(i) for i in picking_ids])],
            }).action_add()
            ruta.invalidate_recordset()
            ruta.action_plan()
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        return {
            'ok': True,
            'nombre': ruta.name,
            'peso': round(ruta.estimated_weight),
            'ocupacion': round(ruta.capacity_usage),
            'sobrecargada': ruta.is_overloaded,
            'mensaje': _("%(ruta)s armada: %(n)s entregas, %(kg)s kg.",
                         ruta=ruta.name, n=len(picking_ids),
                         kg=round(ruta.estimated_weight)),
        }


class AgrogoodCompras(http.Controller):
    """Pizarra de Compras en el telefono.

    Johan trabaja en la feria, de pie, con una mano ocupada. La pizarra del
    escritorio esta bien para planificar la semana; para decidir a quien se le
    compra el tomate mientras se lo estan ofreciendo, hace falta ver la
    solicitud, anotar proveedor y precio, y seguir.

    Se reutiliza el modelo y sus acciones. Lo que cambia es que caben en una
    pantalla y en dos toques.
    """

    def _es_compras(self):
        u = request.env.user
        return (u.has_group('agrogood_base.group_agrogood_purchase')
                or u.has_group('agrogood_base.group_agrogood_general_admin'))

    def _mi_solicitud(self, request_id):
        s = request.env['agrogood.purchase.request'].browse(int(request_id))
        s.check_access('read')
        return s

    @http.route('/agrogood/compras', type='http', auth='user', website=False)
    def compras_home(self, **kw):
        if not self._es_compras():
            return request.redirect('/agrogood/app')
        Req = request.env['agrogood.purchase.request']
        abiertas = Req.search(
            [('state', 'in', ('pending', 'searching', 'quoting', 'partial'))],
            order='priority desc, date_needed, id')
        return request.render('agrogood_pwa.compras_home', {
            # El orden lo decide la urgencia, no la fecha de creacion: lo que
            # se necesita hoy va arriba aunque se haya pedido esta manana.
            'urgentes': abiertas.filtered(
                lambda r: r.priority == '1' or r.is_late),
            'resto': abiertas.filtered(
                lambda r: r.priority != '1' and not r.is_late),
            'listas_para_orden': abiertas.filtered(
                lambda r: r.supplier_id and not r.purchase_order_id),
            'usuario': request.env.user,
        })

    @http.route('/agrogood/compras/<int:request_id>', type='http', auth='user',
                website=False)
    def compras_solicitud(self, request_id, **kw):
        if not self._es_compras():
            return request.redirect('/agrogood/app')
        return request.render('agrogood_pwa.compras_solicitud', {
            'sol': self._mi_solicitud(request_id),
        })

    @http.route('/agrogood/api/compras/proveedores', type='json', auth='user')
    def api_proveedores(self, q='', **kw):
        if not self._es_compras():
            raise AccessError(_("No tienes permiso de Compras."))
        dominio = [('supplier_rank', '>', 0)]
        if q:
            dominio = ['&', ('supplier_rank', '>', 0), ('name', 'ilike', q)]
        return [{'id': p.id, 'nombre': p.name}
                for p in request.env['res.partner'].search(
                    dominio, limit=20, order='name')]

    @http.route('/agrogood/api/compras/anotar', type='json', auth='user')
    def api_anotar(self, request_id, supplier_id=None, price=None, note=None, **kw):
        """Anota proveedor y precio sin cambiar de estado.

        Son los dos datos que Johan consigue en la feria y los unicos que hacen
        falta para poder generar la orden despues. Se guardan por separado del
        cambio de estado porque se consiguen en momentos distintos: primero se
        pregunta el precio, y solo despues se decide si se compra.
        """
        if not self._es_compras():
            raise AccessError(_("No tienes permiso de Compras."))
        sol = self._mi_solicitud(request_id)
        vals = {}
        if supplier_id:
            vals['supplier_id'] = int(supplier_id)
        if price is not None and price != '':
            vals['expected_price'] = float(price)
        if note is not None:
            vals['note'] = (note or '').strip()
        if not vals:
            return {'ok': False, 'mensaje': _("No hay nada que anotar.")}
        try:
            sol.sudo().write(vals)
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        return {'ok': True, 'mensaje': _("Anotado en %s.", sol.name)}

    @http.route('/agrogood/api/compras/estado', type='json', auth='user')
    def api_estado(self, request_id, accion, **kw):
        if not self._es_compras():
            raise AccessError(_("No tienes permiso de Compras."))
        sol = self._mi_solicitud(request_id)
        # Lista blanca: se aceptan solo las acciones de la pizarra. Sin ella,
        # el nombre del metodo llegaria desde el navegador y cualquiera podria
        # invocar lo que quisiera del modelo.
        permitidas = {
            'buscar': 'action_search',
            'cotizar': 'action_quote',
            'no_encontrado': 'action_not_found',
            'rechazar': 'action_reject',
            'reabrir': 'action_reset',
        }
        metodo = permitidas.get(accion)
        if not metodo:
            return {'ok': False, 'mensaje': _("Accion desconocida.")}
        try:
            getattr(sol.sudo(), metodo)()
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        sol.invalidate_recordset()
        estados = dict(sol._fields['state'].selection)
        return {'ok': True, 'estado': estados.get(sol.state, ''),
                'mensaje': _("%(sol)s: %(estado)s",
                             sol=sol.name, estado=estados.get(sol.state, ''))}

    @http.route('/agrogood/api/compras/orden', type='json', auth='user')
    def api_orden(self, request_ids, **kw):
        """Genera las ordenes al proveedor a partir de las solicitudes.

        Se llama al metodo del modelo, que agrupa por proveedor: pedirle tres
        productos al mismo son tres lineas de una orden, no tres ordenes.
        """
        if not self._es_compras():
            raise AccessError(_("No tienes permiso de Compras."))
        if not request_ids:
            return {'ok': False, 'mensaje': _("No has elegido ninguna solicitud.")}
        sols = request.env['agrogood.purchase.request'].browse(
            [int(i) for i in request_ids])
        sols.check_access('read')
        try:
            sols.sudo().action_create_purchase_order()
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        ordenes = sols.mapped('purchase_order_id')
        return {'ok': True, 'mensaje': _(
            "%(n)s orden(es) al proveedor: %(refs)s",
            n=len(ordenes), refs=", ".join(ordenes.mapped('name')))}


class AgrogoodDireccion(http.Controller):
    """La pantalla de Direccion.

    Es distinta de las otras cinco y a proposito: aqui NO se opera, se mira.
    Victor no toma pedidos ni valida albaranes -la matriz de permisos ya se lo
    impide-, asi que la pantalla no tiene un solo boton que cambie nada.

    Y muestra pocas cifras. Un tablero con veinte indicadores se mira una
    semana; con seis se mira todos los dias, que es lo que hace que sirva. Las
    seis elegidas contestan una pregunta cada una:

        cuanto se vendio          - va bien el dia
        cuanto falta por entregar - se va a cumplir
        cuanto falta por cobrar   - hay caja
        cuanto se perdio          - se esta tirando plata
        a cuantos no se factura   - cuanto de lo vendido no se puede cobrar
        que esta en la calle      - donde estan los camiones

    El resto de los numeros vive en los paneles del escritorio, que es donde se
    analiza con tiempo.
    """

    def _es_direccion(self):
        return request.env.user.has_group(
            'agrogood_base.group_agrogood_general_admin')

    @http.route('/agrogood/direccion', type='http', auth='user', website=False)
    def direccion_home(self, **kw):
        if not self._es_direccion():
            return request.redirect('/agrogood/app')

        hoy = fields.Date.context_today(request.env.user)
        inicio_dia = fields.Datetime.to_string(
            fields.Datetime.now().replace(hour=0, minute=0, second=0))
        inicio_mes = hoy.replace(day=1)

        SO = request.env['sale.order']
        vendidas_hoy = SO.search([('date_order', '>=', inicio_dia),
                                  ('state', 'in', ('sale', 'done'))])
        vendidas_mes = SO.search([('date_order', '>=',
                                   fields.Datetime.to_string(
                                       fields.Datetime.to_datetime(inicio_mes))),
                                  ('state', 'in', ('sale', 'done'))])

        # Por entregar: lo confirmado que aun no salio. Es la promesa viva.
        por_entregar = SO.search([('state', '=', 'sale')]).filtered(
            lambda o: o.agrogood_state not in ('delivered', 'invoiced', 'closed',
                                               'cancelled'))

        # Por cobrar, sobre ORDENES DE COMPRA y no sobre facturas. La factura
        # se emite en el portal del SII y en Odoo no existe: mientras esto
        # miraba `account.move`, el panel enseno un cero constante a Direccion,
        # que es la peor forma de estar roto -no parece averiado, parece que no
        # se debe nada-. Ver ADR-006.
        impagas = SO.search([
            ('agrogood_collection_state', 'in', ('open', 'partial')),
        ])
        vencidas = impagas.filtered(
            lambda o: o.agrogood_due_date and o.agrogood_due_date < hoy)

        mermas = request.env['stock.scrap'].search([
            ('state', '=', 'done'), ('write_date', '>=',
                                     fields.Datetime.to_string(
                                         fields.Datetime.to_datetime(inicio_mes)))])

        Socio = request.env['res.partner']
        cartera = Socio.search([('agrogood_business_line_id', '!=', False),
                                ('parent_id', '=', False)])

        return request.render('agrogood_pwa.direccion_home', {
            'hoy_n': len(vendidas_hoy),
            'hoy_monto': sum(vendidas_hoy.mapped('amount_untaxed')),
            'mes_monto': sum(vendidas_mes.mapped('amount_untaxed')),
            'por_entregar_n': len(por_entregar),
            'por_entregar_monto': sum(por_entregar.mapped('amount_untaxed')),
            'por_cobrar': sum(impagas.mapped('agrogood_due_amount')),
            'por_cobrar_n': len(impagas),
            'vencido': sum(vencidas.mapped('agrogood_due_amount')),
            'vencido_n': len(vencidas),
            'merma_monto': sum(mermas.mapped('agrogood_cost')),
            'merma_n': len(mermas),
            'no_facturables': len(cartera.filtered('agrogood_billing_blocked')),
            'cartera_n': len(cartera),
            'rutas': request.env['agrogood.route'].search(
                [('state', '=', 'in_progress')]),
            'llamar': request.env['agrogood.followup'].search_count(
                [('state', '=', 'pending')]),
            'usuario': request.env.user,
        })


class AgrogoodCobranza(http.Controller):
    """Cobranza en el telefono: llamar con el saldo delante.

    Cobrar es una conversacion, no una pantalla de escritorio. Se hace con el
    telefono en la mano, mirando cuanto debe el cliente y desde cuando, y lo
    unico que se anota despues de colgar es que dijo. Todo lo demas -imputar
    abonos, revisar la cartola- se hace sentado y esta en el escritorio.

    El orden es por lo VENCIDO y no por el saldo total. Un cliente que debe
    mucho y no ha vencido nada esta al dia; el que debe poco desde hace dos
    meses es el que se convierte en incobrable. Ordenar por saldo pone arriba
    al primero, que es justo a quien no hay que llamar.
    """

    def _es_cobranza(self):
        u = request.env.user
        return (u.has_group('agrogood_base.group_agrogood_sales')
                or u.has_group('agrogood_base.group_agrogood_general_admin'))

    def _mi_deudor(self, partner_id):
        socio = request.env['res.partner'].browse(int(partner_id))
        socio.check_access('read')
        return socio

    @http.route('/agrogood/cobranza', type='http', auth='user', website=False)
    def cobranza_home(self, **kw):
        if not self._es_cobranza():
            return request.redirect('/agrogood/app')
        hoy = fields.Date.context_today(request.env.user)
        Socio = request.env['res.partner']
        deudores = Socio.search(
            [('agrogood_balance', '>', 0)],
            order='agrogood_overdue_balance desc, agrogood_balance desc')

        # Quien prometio pagar para hoy o para antes y sigue debiendo. Es la
        # lista mas corta y la que mas rinde: ya hubo una conversacion, y
        # volver a llamar el dia que dijo es lo que separa una promesa de una
        # excusa.
        prometieron = deudores.filtered(
            lambda s: s.agrogood_payment_promise_date
            and s.agrogood_payment_promise_date <= hoy)
        vencidos = deudores.filtered(
            lambda s: s.agrogood_overdue_balance > 0 and s not in prometieron)
        al_dia = deudores - prometieron - vencidos

        return request.render('agrogood_pwa.cobranza_home', {
            'prometieron': prometieron,
            'vencidos': vencidos,
            'al_dia': al_dia,
            'total': sum(deudores.mapped('agrogood_balance')),
            'total_vencido': sum(deudores.mapped('agrogood_overdue_balance')),
            'usuario': request.env.user,
        })

    @http.route('/agrogood/cobranza/<int:partner_id>', type='http',
                auth='user', website=False)
    def cobranza_cliente(self, partner_id, **kw):
        if not self._es_cobranza():
            return request.redirect('/agrogood/app')
        socio = self._mi_deudor(partner_id)
        hoy = fields.Date.context_today(request.env.user)
        ordenes = request.env['sale.order'].search([
            ('partner_id', 'child_of', socio.commercial_partner_id.id),
            ('agrogood_collection_state', 'in', ('open', 'partial')),
        ], order='date_order asc')
        abonos = request.env['agrogood.bank.movement'].search([
            ('partner_id', '=', socio.id),
        ], order='date desc', limit=8)
        return request.render('agrogood_pwa.cobranza_cliente', {
            'socio': socio,
            'ordenes': ordenes,
            'abonos': abonos,
            'hoy': hoy,
            'telefono': self._telefono_internacional(socio),
            'usuario': request.env.user,
        })

    def _telefono_internacional(self, socio):
        """El numero en formato internacional, para el enlace de WhatsApp.

        WhatsApp no acepta un numero local: `wa.me/912345678` no abre nada. Se
        antepone el 56 de Chile cuando el numero no trae ya un prefijo, y se
        devuelve vacio si no queda un numero verosimil, para no pintar un boton
        que lleva a una pantalla de error.
        """
        bruto = socio.mobile or socio.phone or ''
        digitos = ''.join(c for c in bruto if c.isdigit())
        if not digitos:
            return ''
        if digitos.startswith('56') and len(digitos) >= 11:
            return digitos
        digitos = digitos.lstrip('0')
        if len(digitos) == 9:
            return '56' + digitos
        return ''

    @http.route('/agrogood/api/cobranza/promesa', type='json', auth='user')
    def api_promesa(self, partner_id, fecha=None, nota=None, **kw):
        """Anota lo que dijo el cliente al colgar."""
        if not self._es_cobranza():
            raise AccessError(_("No tienes permiso de Cobranza."))
        socio = self._mi_deudor(partner_id)
        if not fecha and not (nota or '').strip():
            return {'ok': False,
                    'mensaje': _("Anota al menos la fecha o que dijo.")}
        try:
            socio.sudo().agrogood_registrar_promesa(fecha=fecha or None,
                                                    nota=nota)
        except (UserError, ValidationError) as e:
            return {'ok': False, 'mensaje': str(e)}
        return {'ok': True,
                'mensaje': _("Anotado en %s.", socio.display_name)}
