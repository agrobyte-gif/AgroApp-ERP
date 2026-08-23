"""Endpoint que recibe las posiciones del telefono del conductor.

Diseniado para que un telefono con mala cobertura no pierda datos: acepta
lotes, es idempotente frente a reenvios, y responde rapido para que la app
pueda soltar la conexion y volver a dormirse.
"""

from odoo import _, http
from odoo.http import request


class AgrogoodTracking(http.Controller):

    @http.route('/agrogood/api/driver/positions', type='json', auth='user')
    def registrar_posiciones(self, route_id, positions=None, **kw):
        """Recibe un lote de posiciones de una ruta en curso.

        Solo se aceptan posiciones de una ruta EN CURSO y del conductor que la
        lleva. Las dos comprobaciones importan: la primera evita que la app
        siga reportando despues de terminar la jornada -que es justo lo que
        convierte una herramienta en un rastreador-, y la segunda impide que un
        conductor reporte sobre la ruta de otro.
        """
        ruta = request.env['agrogood.route'].browse(int(route_id))
        ruta.check_access('read')
        if ruta.driver_id != request.env.user:
            return {'ok': False, 'mensaje': _("Esta ruta no es tuya.")}
        if ruta.state != 'in_progress':
            # No es un error: la app puede tener posiciones en cola de antes de
            # cerrar la ruta. Se le dice que pare, y ella deja de insistir.
            return {'ok': True, 'detener': True,
                    'mensaje': _("La ruta ya no esta en curso.")}

        guardadas = request.env['agrogood.driver.position'].sudo()._registrar(
            ruta, positions or [])
        return {
            'ok': True,
            'detener': False,
            'guardadas': len(guardadas),
            'recibidas': len(positions or []),
        }

    @http.route('/agrogood/api/driver/route_state', type='json', auth='user')
    def estado_ruta(self, route_id, **kw):
        """Permite a la app preguntar si debe seguir reportando.

        La app consulta esto al arrancar y de vez en cuando. Sin ello, un
        telefono que perdio la notificacion de cierre seguiria enviando
        posiciones indefinidamente.
        """
        ruta = request.env['agrogood.route'].browse(int(route_id))
        ruta.check_access('read')
        if ruta.driver_id != request.env.user:
            return {'ok': False}
        return {
            'ok': True,
            'estado': ruta.state,
            'rastrear': ruta.state == 'in_progress',
            'paradas_pendientes': ruta.pending_count,
        }

    @http.route('/agrogood/api/driver/my_route', type='json', auth='user')
    def mi_ruta(self, **kw):
        """Devuelve la ruta activa del conductor, si la hay.

        Es lo primero que pregunta la app al abrirse, para saber si debe
        encender el rastreo sin obligar al conductor a navegar hasta su ruta.
        """
        ruta = request.env['agrogood.route'].search([
            ('driver_id', '=', request.env.user.id),
            ('state', '=', 'in_progress'),
        ], limit=1)
        if not ruta:
            return {'ok': True, 'ruta': False}
        return {
            'ok': True,
            'ruta': {
                'id': ruta.id,
                'nombre': ruta.name,
                'paradas': ruta.stop_count,
                'pendientes': ruta.pending_count,
            },
        }


COLORES = ['#1C874F', '#A8720F', '#2563A8', '#9E3226', '#6B3FA0', '#0E7C7B']


class AgrogoodMapa(http.Controller):
    """Pagina de seguimiento para Logistica."""

    def _datos_rutas(self):
        from odoo import fields
        Ruta = request.env['agrogood.route']
        rutas = Ruta.search([('state', '=', 'in_progress')], order='id')
        salida = []
        for i, r in enumerate(rutas):
            posiciones = request.env['agrogood.driver.position'].search(
                [('route_id', '=', r.id)], order='timestamp asc')
            ultima = posiciones[-1] if posiciones else None
            paradas = []
            for s in r.stop_ids:
                if s.latitude and s.longitude:
                    paradas.append({
                        'lat': s.latitude, 'lng': s.longitude,
                        'cliente': s.partner_id.display_name,
                        'direccion': s.street or '',
                        'estado': s.state,
                        'estado_txt': dict(s._fields['state'].selection)[s.state],
                    })
            salida.append({
                'id': r.id,
                'nombre': r.name,
                'conductor': r.driver_id.name or '-',
                'vehiculo': r.vehicle_id.name or '',
                'color': COLORES[i % len(COLORES)],
                'paradas': r.stop_count,
                'entregadas': r.delivered_count,
                'fallidas': r.failed_count,
                'avance': round(r.delivered_count / r.stop_count * 100) if r.stop_count else 0,
                'rastro': [[p.latitude, p.longitude] for p in posiciones],
                'posicion': [ultima.latitude, ultima.longitude] if ultima else None,
                'ultima': fields.Datetime.context_timestamp(
                    r, ultima.timestamp).strftime('%H:%M') if ultima else None,
                'bateria': ultima.battery if ultima else None,
                'paradas_geo': paradas,
            })
        return salida

    @http.route('/agrogood/mapa', type='http', auth='user', website=False)
    def mapa(self, **kw):
        from odoo import fields
        import json as _json
        if not request.env.user.has_group(
                'agrogood_base.group_agrogood_logistics_manager') and \
           not request.env.user.has_group(
                'agrogood_base.group_agrogood_general_admin'):
            return request.redirect('/odoo')
        rutas = self._datos_rutas()
        return request.render('agrogood_tracking.mapa_rutas', {
            'rutas': rutas,
            'datos_json': _json.dumps({'rutas': rutas}),
            'fecha': fields.Date.to_string(fields.Date.context_today(request.env.user)),
        })

    @http.route('/agrogood/api/tracking/rutas', type='json', auth='user')
    def api_rutas(self, **kw):
        return {'rutas': self._datos_rutas()}
