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
        rol = self._rol()
        if rol == 'picker':
            return request.redirect('/agrogood/picker')
        if rol == 'driver':
            return request.redirect('/agrogood/driver')
        return request.render('agrogood_pwa.sin_rol', {})

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
