import logging
import os

from odoo import api, models
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)


class AgrogoodEstaticos(models.AbstractModel):
    """Marca de version para los archivos estaticos de las paginas propias.

    Odoo sirve todo lo que cuelga de `static/` con `Cache-Control: max-age=604800`,
    es decir SIETE DIAS. Nuestras paginas -la PWA del Picker y del Conductor, y
    el mapa de seguimiento- enlazan su CSS y su JS por una ruta fija, sin nada
    que distinga una version de otra. La consecuencia es que un telefono que
    guardo el `pwa.js` del martes lo sigue ejecutando hasta el martes siguiente,
    aunque el servidor ya tenga la correccion.

    Eso vacia de sentido la decision de fondo de este proyecto: la pantalla del
    conductor vive en el servidor precisamente para que un arreglo le llegue sin
    pasar por la tienda de aplicaciones. Si llega pero tarda una semana, no
    llega. Y el sintoma es de los peores que hay: el conductor ve una pantalla
    rota que ya nadie puede reproducir, porque en el resto de los telefonos ya
    se arreglo.

    La solucion es colgar de la URL la fecha de modificacion del propio archivo.
    Cambia cuando el archivo cambia, y solo entonces: no invalida la cache en
    cada despliegue, ni la mantiene cuando ya no debe.

    No se usa la version del modulo del manifiesto a proposito. Esa solo cambia
    si alguien se acuerda de subirla, y olvidarse no da error: da un fallo
    silencioso semanas despues.
    """

    _name = 'agrogood.estaticos'
    _description = "Version de los archivos estaticos"

    @api.model
    def version(self, *rutas):
        """Marca comun a varios archivos: la fecha del modificado mas reciente.

        Se usa una sola marca para todo el conjunto en lugar de una por archivo
        porque el CSS y el JS de una pagina se cambian juntos, y dos marcas
        distintas permitirian a un navegador quedarse con el CSS nuevo y el JS
        viejo, que es peor que quedarse con los dos viejos.
        """
        ultima = 0
        for ruta in rutas:
            try:
                ultima = max(ultima, int(os.stat(file_path(ruta)).st_mtime))
            except (OSError, ValueError):
                # Un archivo que falta no debe tumbar la pagina: sin marca el
                # navegador se comporta como hasta ahora, que es el mal menor.
                _logger.warning("No se pudo fechar el archivo estatico %s", ruta)
        return str(ultima)
