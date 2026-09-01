"""Restaura un respaldo en una base aparte y comprueba que esta todo.

No se ejecuta a mano: lo llama `config\\simulacro_restauracion.ps1`, que ademas
arranca Odoo contra la base restaurada al terminar.

    python tools/simulacro_restauracion.py <dump> <zip|""> <base_prueba> <base_viva>
    python tools/simulacro_restauracion.py --limpiar <base_prueba>

Devuelve 0 si el respaldo sirve y 1 si no. Ese codigo es lo que hace que el
simulacro pueda automatizarse: sin el, alguien tiene que leer la salida y
decidir, y eso no se hace.
"""

import os
import re
import subprocess
import sys
import zipfile

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Lo que se compara. No son todas las tablas a proposito: son las que duelen si
# faltan, y cada una responde a una pregunta distinta -datos maestros,
# operacion, contabilidad, adjuntos, configuracion-. Una comparacion de las 737
# tablas dice menos: se vuelve ruido y nadie la lee.
COMPARAR = [
    ("clientes con linea comercial",
     "SELECT count(*) FROM res_partner WHERE agrogood_business_line_id IS NOT NULL"),
    ("clientes con RUT", "SELECT count(*) FROM res_partner WHERE vat IS NOT NULL"),
    ("productos", "SELECT count(*) FROM product_template"),
    ("tarifas", "SELECT count(*) FROM product_pricelist"),
    ("usuarios", "SELECT count(*) FROM res_users"),
    ("pedidos de venta", "SELECT count(*) FROM sale_order"),
    ("albaranes", "SELECT count(*) FROM stock_picking"),
    ("movimientos de stock", "SELECT count(*) FROM stock_move"),
    ("apuntes de valoracion", "SELECT count(*) FROM stock_valuation_layer"),
    ("facturas", "SELECT count(*) FROM account_move"),
    ("identidades de pago", "SELECT count(*) FROM agrogood_payer"),
    ("adjuntos registrados", "SELECT count(*) FROM ir_attachment"),
    ("modulos instalados",
     "SELECT count(*) FROM ir_module_module WHERE state='installed'"),
]


def credenciales():
    conf = open(os.path.join(RAIZ, "config", "odoo.conf"), encoding="utf-8").read()
    return (re.search(r"(?m)^db_user\s*=\s*(.+)$", conf).group(1).strip(),
            re.search(r"(?m)^db_password\s*=\s*(.+)$", conf).group(1).strip())


def conectar(base, usuario, clave, autocommit=False):
    cn = psycopg2.connect(dbname=base, user=usuario, password=clave, host="localhost")
    if autocommit:
        cn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return cn


def borrar_base(base, usuario, clave):
    cn = conectar("postgres", usuario, clave, autocommit=True)
    cur = cn.cursor()
    # Hay que echar a quien este conectado o el DROP se queda esperando.
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (base,))
    cur.execute('DROP DATABASE IF EXISTS "%s"' % base)
    cn.close()


def main():
    usuario, clave = credenciales()

    if sys.argv[1] == "--limpiar":
        borrar_base(sys.argv[2], usuario, clave)
        return 0

    dump, zip_adjuntos, prueba, viva = sys.argv[1:5]

    # --- 1. restaurar en una base aparte ---
    borrar_base(prueba, usuario, clave)
    cn = conectar("postgres", usuario, clave, autocommit=True)
    cn.cursor().execute('CREATE DATABASE "%s"' % prueba)
    cn.close()

    pg_restore = os.path.join("C:" + os.sep, "Program Files", "PostgreSQL",
                              "17", "bin", "pg_restore.exe")
    if not os.path.exists(pg_restore):
        # Distinguir "no encuentro la herramienta" de "el respaldo esta roto"
        # importa: son problemas distintos, y el segundo asusta de verdad.
        print("  No se encuentra pg_restore en %s" % pg_restore)
        print("  El respaldo NO se ha comprobado: falta la herramienta.")
        return 1
    entorno = dict(os.environ, PGPASSWORD=clave)
    # subprocess con lista, no os.system: la ruta de PostgreSQL lleva espacios
    # y cmd se come las comillas, de modo que os.system intentaba ejecutar
    # "C:/Program" y fallaba. El mensaje decia entonces que el respaldo estaba
    # corrupto cuando lo unico roto era la llamada. Un error que senala el
    # sitio equivocado es peor que no decir nada.
    r = subprocess.run(
        [pg_restore, "-U", usuario, "-h", "localhost", "-d", prueba,
         "--no-owner", "--no-privileges", dump],
        env=entorno, capture_output=True, text=True)
    if r.returncode != 0:
        print("  pg_restore fallo (codigo %s):" % r.returncode)
        for linea in (r.stderr or "").splitlines()[:6]:
            print("    %s" % linea)
        return 1

    # --- 2. comparar contenido ---
    print()
    print("%-30s %10s %12s" % ("QUE", "VIVA", "RESTAURADA"))
    fallos = 0
    cn_v = conectar(viva, usuario, clave)
    cn_p = conectar(prueba, usuario, clave)
    for etiqueta, sql in COMPARAR:
        def cuenta(cn):
            try:
                cur = cn.cursor()
                cur.execute(sql)
                return cur.fetchone()[0]
            except Exception:
                cn.rollback()
                return "-"
        a, b = cuenta(cn_v), cuenta(cn_p)
        igual = (a == b)
        if not igual:
            fallos += 1
        print("%-30s %10s %12s  %s" % (etiqueta, a, b, "" if igual else "DISTINTO"))
    cn_v.close()

    # --- 3. los adjuntos, que es donde suele fallar ---
    print()
    if not zip_adjuntos:
        print("SIN ZIP DE ADJUNTOS: las fotos de entrega y las firmas no estan")
        print("respaldadas. La base se restauraria llena de enlaces rotos.")
        fallos += 1
    else:
        dentro = set()
        with zipfile.ZipFile(zip_adjuntos) as f:
            for i in f.infolist():
                if i.file_size > 0:
                    dentro.add(i.filename.replace("\\", "/"))
        cur = cn_p.cursor()
        cur.execute("SELECT store_fname FROM ir_attachment WHERE store_fname IS NOT NULL")
        nombres = [r[0] for r in cur.fetchall() if r[0]]
        faltan = [n for n in nombres
                  if not any(d.endswith(n.replace("\\", "/")) for d in dentro)]
        print("Adjuntos con archivo: %d, encontrados en el respaldo: %d, faltan: %d"
              % (len(nombres), len(nombres) - len(faltan), len(faltan)))
        # El zip suele tener MENOS archivos que adjuntos y es correcto: Odoo
        # deduplica por contenido, de modo que varios adjuntos comparten uno.
        if faltan:
            fallos += 1
            for f_ in faltan[:5]:
                print("   falta: %s" % f_)
    cn_p.close()

    print()
    if fallos:
        print("%d comprobacion(es) fallaron." % fallos)
        return 1
    print("Contenido y adjuntos completos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
