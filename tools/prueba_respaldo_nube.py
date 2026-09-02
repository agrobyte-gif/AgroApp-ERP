"""Prueba del respaldo en Firebase, sin tocar la nube.

    .venv/Scripts/python.exe tools/prueba_respaldo_nube.py

No necesita ni Odoo ni credenciales: comprueba la parte que decide QUE se sube
y con QUE nombre, que es donde un fallo pasa desapercibido. Lo que depende de
la red -que suba, que se verifique el hash, que el bucket este cerrado- se
comprueba de verdad al subir, y por eso ahi se vuelve a leer del bucket en
lugar de fiarse de que la subida no diera error.

Lo que se comprueba, en orden de lo que cuesta si falla:

 1. Que se suba el respaldo MAS RECIENTE. Subir uno viejo sin decirlo deja la
    nube con una copia de hace semanas y a todo el mundo tranquilo.
 2. Que se suban los DOS archivos. Sin el zip de adjuntos, restaurar deja una
    base llena de enlaces rotos a fotos de entrega y firmas.
 3. Que sin credencial explique que hacer en vez de reventar, porque esa es la
    primera pantalla que ve quien lo configura.
"""

import datetime
import io
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subir_respaldo as sr  # noqa: E402

R = []


def paso(t, ok, det=""):
    R.append(ok)
    print("  [%s] %s" % ("OK " if ok else "FALLA", t))
    if det:
        print("        %s" % det)


print("=" * 74)
print("RESPALDO EN LA NUBE")
print("=" * 74)

# ------------------------------------------------- que archivos se suben
print()
print("QUE SE SUBE")

temporal = tempfile.mkdtemp(prefix="agrogood-prueba-")
original = sr.RESPALDOS
sr.RESPALDOS = temporal
try:
    nombres = [
        "agrogood-20260101-0700.dump",
        "agrogood-20260830-0700.dump",
        "adjuntos-20260101-0700.zip",
        "adjuntos-20260830-0700.zip",
        "notas.txt",
    ]
    for i, n in enumerate(nombres):
        ruta = os.path.join(temporal, n)
        io.open(ruta, "w", encoding="utf-8").write("contenido " + n)
        # Las fechas de modificacion decoran el orden: el criterio es la fecha
        # del archivo y no lo que diga su nombre, porque un respaldo copiado a
        # mano puede llamarse cualquier cosa.
        antiguedad = time.time() - (100000 if "20260101" in n else 10)
        os.utime(ruta, (antiguedad, antiguedad))

    elegidos = [os.path.basename(x) for x in sr.ultimos_locales()]
    paso("Se suben dos archivos: la base y los adjuntos",
         len(elegidos) == 2, ", ".join(elegidos))
    paso("Se sube el mas reciente de cada uno, no el primero que aparece",
         "agrogood-20260830-0700.dump" in elegidos
         and "adjuntos-20260830-0700.zip" in elegidos)
    paso("Lo que no es un respaldo no se sube",
         "notas.txt" not in elegidos)

    sr.RESPALDOS = os.path.join(temporal, "no-existe")
    paso("Sin respaldos locales no revienta, devuelve vacio",
         sr.ultimos_locales() == [])

    # En el servidor de produccion los archivos se llaman distinto. La misma
    # herramienta tiene que servir en los dos sitios: dos versiones de esto se
    # separarian, y la que se rompe es siempre la que nadie mira.
    produccion = os.path.join(temporal, "produccion")
    os.makedirs(produccion)
    for n in ("agroapp-20260830-0300.dump", "adjuntos-20260830-0300.tar.gz"):
        io.open(os.path.join(produccion, n), "w", encoding="utf-8").write("x")
    sr.RESPALDOS = produccion
    elegidos = sorted(os.path.basename(x) for x in sr.ultimos_locales())
    paso("Reconoce tambien los nombres del servidor de produccion",
         elegidos == ["adjuntos-20260830-0300.tar.gz",
                      "agroapp-20260830-0300.dump"],
         ", ".join(elegidos))
finally:
    sr.RESPALDOS = original
    shutil.rmtree(temporal, ignore_errors=True)

# ------------------------------------------------------------ el nombre
print()
print("DONDE SE GUARDA")

hoy = datetime.date.today()
ruta = sr.ruta_en_bucket("agrogood-20260830-0700.dump")
paso("Va ordenado por ano y mes",
     ruta == "respaldos/%04d/%02d/agrogood-20260830-0700.dump"
     % (hoy.year, hoy.month), ruta)
paso("Conserva el nombre del archivo",
     ruta.endswith("agrogood-20260830-0700.dump"),
     "asi se reconoce cual es sin abrirlo")

# --------------------------------------------------------------- el hash
print()
print("LA COMPROBACION DE CONTENIDO")

f = tempfile.NamedTemporaryFile(delete=False, suffix=".dump")
f.write(b"agrogood" * 1000)
f.close()
try:
    import base64
    import hashlib
    esperado = base64.b64encode(hashlib.md5(b"agrogood" * 1000).digest()).decode()
    paso("El hash se calcula como lo calcula Google, en base64",
         sr.md5_local(f.name) == esperado, sr.md5_local(f.name))

    with io.open(f.name, "ab") as g:
        g.write(b"x")
    paso("Un archivo cambiado da un hash distinto",
         sr.md5_local(f.name) != esperado,
         "es lo que detecta una subida a medias")
finally:
    os.unlink(f.name)

# ------------------------------------------------------- sin credencial
print()
print("SIN CONFIGURAR")

clave_real = sr.CLAVE
sr.CLAVE = os.path.join(tempfile.gettempdir(), "no-hay-clave-aqui.json")
try:
    print("  --- lo que se ve al ejecutarlo sin configurar: ---")
    resultado = sr.conectar()
    paso("Explica que hacer en vez de reventar", resultado is None)
finally:
    sr.CLAVE = clave_real

paso("La credencial no se versiona",
     os.system('git -C "%s" check-ignore -q config/firebase-clave.json'
               % os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) == 0,
     "esta en .gitignore")

print()
print("=" * 74)
print("%d de %d comprobaciones" % (sum(1 for x in R if x), len(R)))
print("=" * 74)
print("El respaldo sube lo que debe." if all(R) else "HAY FALLOS. Revisar arriba.")
sys.exit(0 if all(R) else 1)
