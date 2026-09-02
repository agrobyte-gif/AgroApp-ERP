"""Lee el archivo que exporta el banco. Sin ORM: solo interpreta el archivo.

Vive aparte del modelo a proposito. Interpretar una planilla de banco es un
problema de formatos -cabeceras corridas, montos con signo peso, fechas de tres
maneras- y se prueba mejor solo, sin base de datos delante.

Lo que se midio sobre una cartola real de Agrogood (marzo, tres cuentas, 14.362
filas; no se importo ni un registro):

* **Los tres bancos traen el RUT del pagador.** Scotiabank en columna propia.
  Santander lo pone al principio de la descripcion, relleno de ceros hasta once
  digitos: `00763341712` es `76334171-2`. El 95% de sus abonos lo llevan ahi.
  Buscarlo escrito como `77.716.841-K` fue lo que hizo creer que no venia.
* La columna CLIENTE ya viene rellena a mano en el 99% de los abonos. Es el
  vocabulario de Agrogood -BAR CALLEJON, HOP, LOCO JOE-, no el nombre fiscal.
"""

import re
from datetime import date, datetime

# Como se reconoce cada banco: por lo que dice su cabecera, no por el nombre de
# la hoja. El nombre de la hoja lo pone quien exporta y cambia; la cabecera la
# pone el banco.
SENAL_SCOTIABANK = "RUT ORIGEN"
SENAL_SANTANDER = "CARGO/ABONO"

# Cada columna que interesa y como puede venir escrita. Se compara por prefijo
# porque el archivo llega con la codificacion rota: "DESCRIPCION MOVIMIENTO"
# aparece como "DESCRIPCI?N MOVIMIENTO", y "N? DOCUMENTO" igual.
COLUMNAS = {
    'fecha': ["FECHA"],
    'monto': ["MONTO"],
    'rut': ["RUT ORIGEN"],
    'nombre': ["NOMBRE"],
    'alias': ["CLIENTE"],
    'descripcion': ["DESCRIPCI"],
    'signo': ["CARGO/ABONO"],
    'cuenta_origen': ["CTA. ORIGEN", "CTA ORIGEN"],
    'banco_origen': ["BANCO ORIGEN"],
    'tipo': ["TIPO"],
}

# Lo que Agrogood escribe en la columna CLIENTE cuando el movimiento NO viene
# de un cobro. No son clientes y no deben aprenderse como alias.
NO_SON_CLIENTES = ('CARGO', 'VENTA', 'ABONO', 'TRASPASO', 'CIERRE')


def _texto(valor):
    return re.sub(r"[ ]+", " ", str(valor if valor is not None else "").strip())


def digito_verificador(cuerpo):
    suma, mult = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * mult
        mult = 2 if mult == 7 else mult + 1
    resto = 11 - (suma % 11)
    return {11: '0', 10: 'K'}.get(resto, str(resto))


def leer_rut(bruto):
    """Devuelve `12345678-9`, o None si eso no es un RUT.

    Se quitan los ceros de la izquierda antes de comprobar nada: Santander
    rellena hasta once digitos y `00763341712` tiene que dar el mismo resultado
    que `76.334.171-2`. Si no, el mismo pagador entra como dos pagadores.

    El digito verificador se comprueba siempre. En la descripcion de Santander
    hay tambien numeros de documento y de cuenta en la misma posicion, y sin
    esa comprobacion se convertirian en RUT inventados.
    """
    limpio = re.sub(r"[^0-9kK]", "", str(bruto or "")).upper().lstrip("0")
    if len(limpio) < 8 or len(limpio) > 9 or not limpio[:-1].isdigit():
        return None
    cuerpo, verificador = limpio[:-1], limpio[-1]
    if digito_verificador(cuerpo) != verificador:
        return None
    return "%s-%s" % (cuerpo, verificador)


def leer_monto(bruto):
    """El monto, venga como numero o como `$ 49.000`."""
    if isinstance(bruto, (int, float)):
        return float(bruto)
    texto = re.sub(r"[^0-9-]", "", str(bruto or ""))
    if texto in ("", "-"):
        return 0.0
    return float(texto)


def leer_fecha(bruto):
    """La fecha, como date. None si esa celda no es una fecha.

    Es tambien el filtro que descarta las filas basura: la cartola de
    Scotiabank trae dentro de la misma hoja un segundo bloque con las columnas
    corridas, y ahi donde deberia ir la fecha hay cualquier cosa. Una fila sin
    fecha legible no se interpreta: se salta.
    """
    if isinstance(bruto, datetime):
        return bruto.date()
    if isinstance(bruto, date):
        return bruto
    texto = _texto(bruto)
    for formato in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _cabecera(fila):
    """Mapa nombre_interno -> indice de columna, y la fila en texto."""
    celdas = [_texto(c).upper() for c in fila]
    mapa = {}
    for clave, prefijos in COLUMNAS.items():
        for i, celda in enumerate(celdas):
            if celda and any(celda.startswith(p) for p in prefijos):
                mapa.setdefault(clave, i)
                break
    return mapa, celdas


def detectar(celdas):
    """Que banco es, mirando la cabecera."""
    texto = " | ".join(celdas)
    if SENAL_SCOTIABANK in texto:
        return 'scotiabank'
    if SENAL_SANTANDER in texto:
        return 'santander'
    return None


def leer_hoja(filas, nombre_hoja=""):
    """Convierte una hoja en abonos. Devuelve (lista, descartes).

    `filas` es cualquier iterable de tuplas -lo que da openpyxl con
    values_only-. Solo salen ABONOS: un cargo es dinero que sale y no lo paga
    ningun cliente.
    """
    filas = list(filas)
    mapa, banco, inicio = {}, None, 0
    for i, fila in enumerate(filas[:20]):
        posible, celdas = _cabecera(fila)
        detectado = detectar(celdas)
        if detectado and 'fecha' in posible and 'monto' in posible:
            mapa, banco, inicio = posible, detectado, i + 1
            break
    if not banco:
        return [], {'sin_cabecera': 1}

    abonos = []
    descartes = {'sin_fecha': 0, 'cargos': 0}
    vistos = {}
    for fila in filas[inicio:]:

        def celda(clave):
            i = mapa.get(clave)
            return fila[i] if i is not None and i < len(fila) else None

        fecha = leer_fecha(celda('fecha'))
        if not fecha:
            descartes['sin_fecha'] += 1
            continue
        monto = leer_monto(celda('monto'))
        # Santander marca el sentido en una columna; Scotiabank exporta solo
        # abonos, y ahi el sentido lo da el signo del monto.
        signo = _texto(celda('signo')).upper()
        if monto <= 0 or (signo and signo != 'A'):
            descartes['cargos'] += 1
            continue

        descripcion = _texto(celda('descripcion'))
        rut = leer_rut(celda('rut'))
        if not rut and descripcion:
            # Santander: el RUT es la primera palabra de la descripcion. Solo
            # la primera: mas adelante hay numeros de cuenta que podrian pasar
            # por RUT de casualidad.
            partes = descripcion.split()
            if partes:
                rut = leer_rut(partes[0])

        alias = _texto(celda('alias')).upper()
        if alias in NO_SON_CLIENTES:
            alias = ''

        registro = {
            'banco': banco,
            'hoja': nombre_hoja,
            'fecha': fecha,
            'monto': monto,
            'rut': rut,
            'alias': alias,
            'nombre_banco': _texto(celda('nombre')),
            'descripcion': descripcion or _texto(celda('tipo')),
            'cuenta_origen': _texto(celda('cuenta_origen')),
        }
        # Dos transferencias iguales el mismo dia del mismo pagador existen de
        # verdad. Se numeran para poder distinguirlas: asi volver a subir el
        # archivo no duplica nada, y un pago repetido de verdad si entra.
        base = "%s|%s|%.0f|%s|%s" % (banco, fecha, monto, rut or '', alias)
        vistos[base] = vistos.get(base, 0) + 1
        registro['clave'] = "%s#%d" % (base, vistos[base])
        abonos.append(registro)

    return abonos, descartes
