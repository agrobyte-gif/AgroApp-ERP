"""Sube el ultimo respaldo a Firebase y comprueba que llego entero.

    python tools/subir_respaldo.py                 informa que hay en la nube
    AGROGOOD_FIREBASE=subir python tools/subir_respaldo.py    sube el ultimo

No necesita Odoo: trabaja sobre los archivos que deja `respaldar_local.ps1`.
Lo llama ese mismo script al terminar, de modo que a mano solo se ejecuta para
comprobar.

Por que Firebase y no solo OneDrive: la carpeta de OneDrive cuelga de la cuenta
personal de quien tiene el equipo. Si esa persona se va, cambia de cuenta o
llena su espacio, los respaldos se van con ella y nadie se entera. El bucket es
del proyecto, no de una persona.

QUE HACE FALTA, una sola vez:

  1. Crear un proyecto en https://console.firebase.google.com
  2. Activar Storage. Puede pedir activar facturacion; con 150 MB al dia el
     coste es de centavos, pero conviene mirarlo antes de decir que si.
  3. Configuracion del proyecto > Cuentas de servicio > Generar clave privada.
  4. Guardar ese archivo como  config/firebase-clave.json
     (esta en .gitignore: es una credencial y no se versiona nunca)

El nombre del bucket se deduce del proyecto. Si no acierta, se le dice:
     AGROGOOD_FIREBASE_BUCKET=mi-proyecto.firebasestorage.app

LO QUE SE COMPRUEBA DESPUES DE SUBIR

Subir un archivo y dar por hecho que llego es la forma habitual de descubrir el
dia malo que el respaldo estaba a medias. Aqui se vuelve a leer del bucket y se
comparan tamano y hash MD5 contra el archivo local. Y se comprueba ademas que
NO se pueda descargar sin credenciales: el respaldo lleva los RUT, telefonos,
direcciones y deudas de 157 clientes, y un bucket abierto los publica en
internet sin que nadie lo note.
"""

import base64
import datetime
import hashlib
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESPALDOS = os.environ.get("AGROGOOD_RESPALDOS") or os.path.join(RAIZ, "respaldos")
CLAVE = (os.environ.get("AGROGOOD_FIREBASE_CLAVE")
         or os.path.join(RAIZ, "config", "firebase-clave.json"))
SUBIR = os.environ.get("AGROGOOD_FIREBASE") == "subir"

# Cuantas copias se conservan en la nube. Menos que en el disco local a
# proposito: la nube es red de seguridad, no archivo historico.
CONSERVAR = 30

PREFIJO = "respaldos"

# Los dos archivos que forman un respaldo completo, y como se llaman en cada
# sitio: en este equipo `agrogood-*.dump` y `adjuntos-*.zip`; en el servidor de
# produccion `agroapp-*.dump` y `adjuntos-*.tar.gz`. Se aceptan los dos juegos
# de nombres para que la misma herramienta valga en los dos, en lugar de tener
# dos versiones que se van separando.
GRUPOS = {
    "base": ("agrogood-", "agroapp-"),
    "adjuntos": ("adjuntos-",),
}


def humano(n):
    return "%.1f MB" % (n / 1048576.0)


def md5_local(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1024 * 1024), b""):
            h.update(trozo)
    return base64.b64encode(h.digest()).decode()


def ultimos_locales():
    """La base y los adjuntos MAS RECIENTES que dejo el script de respaldo.

    Se elige por fecha del archivo y no por lo que diga su nombre: un respaldo
    copiado a mano puede llamarse cualquier cosa, y subir uno viejo sin decirlo
    deja la nube con una copia de hace semanas y a todo el mundo tranquilo.
    """
    if not os.path.isdir(RESPALDOS):
        return []
    salida = []
    for prefijos in GRUPOS.values():
        candidatos = [f for f in os.listdir(RESPALDOS)
                      if f.startswith(prefijos)]
        if candidatos:
            nombre = max(candidatos, key=lambda f: os.path.getmtime(
                os.path.join(RESPALDOS, f)))
            salida.append(os.path.join(RESPALDOS, nombre))
    return salida


def conectar():
    """Devuelve el bucket, o None diciendo por que no se pudo."""
    try:
        import firebase_admin
        from firebase_admin import credentials, storage
    except ImportError:
        print("Falta la libreria. Se instala con:")
        print("   .venv/Scripts/python.exe -m pip install firebase-admin")
        return None

    if not os.path.exists(CLAVE):
        print("No esta la credencial: %s" % CLAVE)
        print()
        print("Se descarga una sola vez desde la consola de Firebase:")
        print("  Configuracion del proyecto > Cuentas de servicio")
        print("  > Generar nueva clave privada")
        print()
        print("Ese archivo es una credencial. Va en config/, que esta en")
        print(".gitignore, y no se manda por correo ni por WhatsApp.")
        return None

    datos = json.load(open(CLAVE, encoding="utf-8"))
    proyecto = datos.get("project_id")
    if not proyecto:
        print("El archivo %s no parece una clave de cuenta de servicio." % CLAVE)
        return None

    cred = credentials.Certificate(CLAVE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    # Firebase cambio la forma del nombre: los proyectos nuevos terminan en
    # .firebasestorage.app y los viejos en .appspot.com. Se prueban los dos en
    # vez de preguntar, porque quien crea el proyecto no tiene por que saber
    # cual le toco.
    candidatos = [os.environ.get("AGROGOOD_FIREBASE_BUCKET")] if \
        os.environ.get("AGROGOOD_FIREBASE_BUCKET") else [
            "%s.firebasestorage.app" % proyecto,
            "%s.appspot.com" % proyecto,
        ]
    for nombre in candidatos:
        try:
            bucket = storage.bucket(nombre)
            bucket.reload()
            print("Proyecto: %s" % proyecto)
            print("Bucket  : %s" % nombre)
            return bucket
        except Exception:
            continue
    print("No se encontro el bucket del proyecto %s." % proyecto)
    print("Puede que Storage no este activado todavia, o que el bucket se")
    print("llame de otra forma. Se le puede decir cual con:")
    print("   AGROGOOD_FIREBASE_BUCKET=nombre-exacto.firebasestorage.app")
    return None


def ruta_en_bucket(nombre):
    """Ordenado por ano y mes: listar una carpeta con cientos de archivos
    sueltos es incomodo justo el dia que hay prisa."""
    fecha = datetime.date.today()
    return "%s/%04d/%02d/%s" % (PREFIJO, fecha.year, fecha.month, nombre)


def esta_publico(bucket, blob):
    """True si el respaldo se puede bajar SIN credenciales.

    Se comprueba de verdad, pidiendolo como lo pediria un desconocido, en vez
    de mirar permisos. Un bucket mal configurado publica en internet los RUT,
    telefonos, direcciones y deudas de toda la cartera, y no avisa.
    """
    import requests
    url = ("https://storage.googleapis.com/%s/%s"
           % (bucket.name, blob.name.replace(" ", "%20")))
    try:
        r = requests.get(url, timeout=15, stream=True)
        return r.status_code == 200
    except requests.RequestException:
        # Sin internet no se puede afirmar que este cerrado. Se dice.
        return None


def subir(bucket, ruta_local):
    nombre = os.path.basename(ruta_local)
    destino = ruta_en_bucket(nombre)
    tam = os.path.getsize(ruta_local)
    print()
    print("  %s  (%s)" % (nombre, humano(tam)))

    blob = bucket.blob(destino)
    blob.upload_from_filename(ruta_local)

    # Volver a leerlo del bucket, no fiarse de que la subida no diera error.
    comprobado = bucket.get_blob(destino)
    if comprobado is None:
        print("     FALLO: subio sin error pero no esta en el bucket.")
        return False
    if comprobado.size != tam:
        print("     FALLO: alla pesa %s y aca %s."
              % (humano(comprobado.size or 0), humano(tam)))
        return False
    esperado = md5_local(ruta_local)
    if comprobado.md5_hash and comprobado.md5_hash != esperado:
        print("     FALLO: el contenido no coincide. Llego corrupto.")
        return False
    print("     subido y verificado: mismo tamano y mismo contenido")

    abierto = esta_publico(bucket, comprobado)
    if abierto is True:
        print()
        print("     AVISO GRAVE: este respaldo se puede descargar sin clave.")
        print("     Lleva los RUT, telefonos y deudas de toda la cartera.")
        print("     Hay que cerrar el bucket en la consola de Firebase antes")
        print("     de seguir usando esto.")
    elif abierto is None:
        print("     (no se pudo comprobar si esta cerrado: sin conexion)")
    else:
        print("     cerrado: no se descarga sin credenciales")
    return True


def rotar(bucket):
    """Deja solo las CONSERVAR copias mas recientes de cada tipo."""
    borrados = 0
    for prefijos in GRUPOS.values():
        blobs = [b for b in bucket.list_blobs(prefix=PREFIJO + "/")
                 if os.path.basename(b.name).startswith(prefijos)]
        blobs.sort(key=lambda b: b.time_created, reverse=True)
        for b in blobs[CONSERVAR:]:
            b.delete()
            borrados += 1
    return borrados


def informar(bucket):
    blobs = list(bucket.list_blobs(prefix=PREFIJO + "/"))
    if not blobs:
        print()
        print("No hay ningun respaldo en la nube todavia.")
        return
    blobs.sort(key=lambda b: b.time_created, reverse=True)
    total = sum(b.size or 0 for b in blobs)
    print()
    print("Copias en la nube: %d  (%s en total)" % (len(blobs), humano(total)))

    ultimo = blobs[0]
    ahora = datetime.datetime.now(datetime.timezone.utc)
    horas = (ahora - ultimo.time_created).total_seconds() / 3600.0
    print("La mas reciente: %s, hace %.0f horas"
          % (os.path.basename(ultimo.name), horas))
    # Un respaldo viejo es la forma silenciosa de no tener respaldo: la tarea
    # dejo de correr hace semanas y el archivo sigue ahi, tranquilizando.
    if horas > 48:
        print()
        print("AVISO: el respaldo mas nuevo tiene mas de dos dias. Puede que")
        print("la tarea programada haya dejado de correr. Se revisa con:")
        print("   Get-ScheduledTask -TaskName 'Agroapp*'")
    print()
    for b in blobs[:6]:
        print("   %-34s %10s   %s"
              % (os.path.basename(b.name), humano(b.size or 0),
                 b.time_created.strftime("%Y-%m-%d %H:%M")))


def main():
    print("=" * 74)
    print("RESPALDO EN FIREBASE" + ("  [SUBIENDO]" if SUBIR else "  [SOLO INFORME]"))
    print("=" * 74)

    bucket = conectar()
    if bucket is None:
        return 1

    if SUBIR:
        archivos = ultimos_locales()
        if not archivos:
            print()
            print("No hay ningun respaldo local que subir. Se genera con:")
            print("   config\\respaldar_local.ps1")
            return 1
        ok = all(subir(bucket, a) for a in archivos)
        borrados = rotar(bucket)
        if borrados:
            print()
            print("Se borraron %d copias antiguas (se conservan %d)."
                  % (borrados, CONSERVAR))
        informar(bucket)
        if not ok:
            print()
            print("ALGO NO SUBIO BIEN. El respaldo de la nube no sirve tal cual.")
            return 1
        return 0

    informar(bucket)
    print()
    print("=" * 74)
    print("SOLO INFORME. Para subir el ultimo respaldo:")
    print("   AGROGOOD_FIREBASE=subir python tools/subir_respaldo.py")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
